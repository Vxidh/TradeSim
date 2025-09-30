#pragma once

#include <map>
#include <vector>
#include <memory>
#include <string>
#include <cstdint>
#include "Order.h"

class OrderBook {
public:
    using OrderPtr = std::unique_ptr<Order>;

    OrderBook(std::string symbol) : symbol_(std::move(symbol)), next_trade_id_(1) {}

    // add/cancel
    std::vector<Trade> addOrder(OrderPtr order);
    void cancelOrder(int32_t orderId);

    // access
    const std::map<double, PriceLevel, std::greater<double>>& getBids() const;
    const std::map<double, PriceLevel>& getAsks() const;

private:
    std::string symbol_;
    int32_t next_trade_id_;

    std::map<double, PriceLevel, std::greater<double>> bids_;
    std::map<double, PriceLevel> asks_;

    std::map<int32_t, OrderPtr> orders_by_id_;
    std::vector<Order*> stop_orders_;
    std::vector<Order*> pending_triggered_stops_;

    // core logic
    std::vector<Trade> match(Order* aggressing_order);
    void addLimitOrder(Order* order);
    void checkStopOrders(const Trade& trade);
    void processPendingTriggeredStops(std::vector<Trade>& trades_made);
};
