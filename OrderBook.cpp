#include "OrderBook.h"
#include "Order.h"
#include <unordered_map>

using namespace std;

struct Order;

void OrderBook::addOrder(unique_ptr<Order> order) {
    if(order->type != OrderType::Limit){
        return;
    }

    if(order->side == Side::Buy){
        bids_[order->price].push_back(move(order));
    } else if(order->side == Side::Sell){
        asks_[order->price].push_back(move(order));
    }

}

void OrderBook::cancelOrder(int orderId) {
    
}

const map<double, PriceLevel>& OrderBook::getBids() const {
    return bids_;
}

const map<double, PriceLevel>& OrderBook::getAsks() const {
    return asks_;
}