#pragma once

#include <deque>
#include <map>
#include <memory>
#include <string>
#include <unordered_map>

#include "Order.h"

using PriceLevel = std::deque<std::unique_ptr<Order>>;

class OrderBook {
public:
    void addOrder(std::unique_ptr<Order> order);
    void cancelOrder(int orderId);
    const std::map<double, PriceLevel>& getBids() const;
    const std::map<double, PriceLevel>& getAsks() const;
    
private:
    std::map<double, PriceLevel> bids_;
    std::map<double, PriceLevel> asks_;
    std::unordered_map<int32_t, Order*> orders_by_id_;
};