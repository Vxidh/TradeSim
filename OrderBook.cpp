#include "OrderBook.h"
#include <iostream>
#include <algorithm>
#include <vector>
#include <chrono>

using namespace std;

static int64_t currentTimestamp() {
    return chrono::duration_cast<chrono::milliseconds>(
               chrono::system_clock::now().time_since_epoch()
           ).count();
}

vector<Trade> OrderBook::addOrder(OrderPtr order) {
    Order* order_ptr = order.get();
    orders_by_id_[order->orderId] = std::move(order);

    switch (order_ptr->type) {
        case OrderType::Market:
        case OrderType::Limit:
            return match(order_ptr);
        case OrderType::Stop:
        case OrderType::StopLimit:
            stop_orders_.push_back(order_ptr);
            return {};
    }
    return {};
}

void OrderBook::cancelOrder(int32_t orderId) {
    auto order_it = orders_by_id_.find(orderId);
    if (order_it == orders_by_id_.end()) {
        return;
    }

    Order* order = order_it->second.get();

    if (order->side == Side::Buy) {
        auto level_it = bids_.find(order->price);
        if (level_it != bids_.end()) {
            level_it->second.erase(order->position_in_book);
            if (level_it->second.empty()) {
                bids_.erase(level_it);
            }
        }
    } else {
        auto level_it = asks_.find(order->price);
        if (level_it != asks_.end()) {
            level_it->second.erase(order->position_in_book);
            if (level_it->second.empty()) {
                asks_.erase(level_it);
            }
        }
    }

    orders_by_id_.erase(order_it);
    cout << "Cancelled order " << orderId << endl;
}

vector<Trade> OrderBook::match(Order* aggressing_order) {
    vector<Trade> trades_made;

    if (aggressing_order->side == Side::Buy) {
        auto ask_level_it = asks_.begin();
        while (aggressing_order->quantity > 0 && ask_level_it != asks_.end()) {
            double best_ask_price = ask_level_it->first;
            PriceLevel& resting_orders = ask_level_it->second;

            if (aggressing_order->type == OrderType::Limit && aggressing_order->price < best_ask_price) {
                break;
            }

            auto resting_it = resting_orders.begin();
            //aggressing_order->quantity > 0 is to make sure that as long as our buyer wants to buy shares we still have sellers
            while (aggressing_order->quantity > 0 && resting_it != resting_orders.end()) {
                Order* resting_order = *resting_it;
                int32_t trade_quantity = min(aggressing_order->quantity, resting_order->quantity);

                trades_made.push_back({next_trade_id_++, aggressing_order->orderId, resting_order->orderId,
                                       aggressing_order->symbol, best_ask_price, trade_quantity, currentTimestamp()});

                aggressing_order->quantity -= trade_quantity;
                resting_order->quantity -= trade_quantity;

                if (resting_order->quantity == 0) {
                    // erase via iterator to stay safe
                    resting_it = resting_orders.erase(resting_it);
                    orders_by_id_.erase(resting_order->orderId);
                } else {
                    ++resting_it;
                }
            }

            if (resting_orders.empty()) {
                ask_level_it = asks_.erase(ask_level_it);
            } else {
                ++ask_level_it;
            }
        }
    } else {
        auto bid_level_it = bids_.begin();
        while (aggressing_order->quantity > 0 && bid_level_it != bids_.end()) {
            double best_bid_price = bid_level_it->first;
            PriceLevel& resting_orders = bid_level_it->second;

            if (aggressing_order->type == OrderType::Limit && aggressing_order->price > best_bid_price) {
                break;
            }

            auto resting_it = resting_orders.begin();
            while (aggressing_order->quantity > 0 && resting_it != resting_orders.end()) {
                Order* resting_order = *resting_it;
                int32_t trade_quantity = min(aggressing_order->quantity, resting_order->quantity);

                trades_made.push_back({next_trade_id_++, aggressing_order->orderId, resting_order->orderId,
                                       aggressing_order->symbol, best_bid_price, trade_quantity, currentTimestamp()});

                aggressing_order->quantity -= trade_quantity;
                resting_order->quantity -= trade_quantity;

                if (resting_order->quantity == 0) {
                    resting_it = resting_orders.erase(resting_it);
                    orders_by_id_.erase(resting_order->orderId);
                } else {
                    ++resting_it;
                }
            }

            if (resting_orders.empty()) {
                bid_level_it = bids_.erase(bid_level_it);
            } else {
                ++bid_level_it;
            }
        }
    }

    // leftover handling
    if (aggressing_order->quantity > 0) {
        if (aggressing_order->type == OrderType::Limit) {
            addLimitOrder(aggressing_order);
        } else { // market leftover
            orders_by_id_.erase(aggressing_order->orderId);
        }
    }

    // queue stop triggers for each trade
    for (const auto& trade : trades_made) {
        checkStopOrders(trade);
    }

    // process pending triggered stops safely and collect their trades
    processPendingTriggeredStops(trades_made);

    return trades_made;
}

void OrderBook::addLimitOrder(Order* order) {
    PriceLevel* level;
    if (order->side == Side::Buy) {
        level = &bids_[order->price];
    } else {
        level = &asks_[order->price];
    }
    level->push_back(order);
    order->position_in_book = prev(level->end());
}

void OrderBook::checkStopOrders(const Trade& trade) {
    //Assume that all trades happen at 150$ and I want to buy at 145$. In this case I need an option where the order needs to be dormant without interfering with the main asks_ map.

    vector<Order*> to_trigger;
    to_trigger.reserve(stop_orders_.size());

    for (auto* stop_order : stop_orders_) {
        if (stop_order->side == Side::Buy) {
            if (trade.price >= stop_order->stopPrice) {
                to_trigger.push_back(stop_order);
            }
        } else {
            if (trade.price <= stop_order->stopPrice) {
                to_trigger.push_back(stop_order);
            }
        }
    }

    // remove triggered from stop_orders_, convert types, and push to pending queue
    for (auto* o : to_trigger) {
        stop_orders_.erase(std::remove(stop_orders_.begin(), stop_orders_.end(), o), stop_orders_.end());
        if (o->type == OrderType::Stop) {
            o->type = OrderType::Market;
        } else if (o->type == OrderType::StopLimit) {
            o->type = OrderType::Limit;
        }
        pending_triggered_stops_.push_back(o);
    }
}

void OrderBook::processPendingTriggeredStops(std::vector<Trade>& trades_made) {
    while (!pending_triggered_stops_.empty()) {
        auto current_batch = std::move(pending_triggered_stops_);
        pending_triggered_stops_.clear();

        for (auto* stop_order : current_batch) {
            auto new_trades = match(stop_order);
            if (!new_trades.empty()) {
                trades_made.insert(trades_made.end(), new_trades.begin(), new_trades.end());
            }

            // if the triggered order still has leftover quantity and is a limit, match() will have called addLimitOrder()
            // so nothing more to do here. if it was a market leftover, match removed it from orders_by_id_.
        }
        // if checkStopOrders was invoked during those matches and pushed more stops, the while loop will run again.
    }
}

const map<double, PriceLevel, greater<double>>& OrderBook::getBids() const {
    return bids_;
}

const map<double, PriceLevel>& OrderBook::getAsks() const {
    return asks_;
}
