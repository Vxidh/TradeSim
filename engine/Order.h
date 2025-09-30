#pragma once

#include <string>
#include <utility>
#include <cstdint> 
#include <list> // Switched from deque to list for stable iterators

// Forward declare Order so we can use it in the PriceLevel alias
struct Order; 
using PriceLevel = std::list<Order*>;

enum class Side {
    Buy,
    Sell
};

enum class OrderType {
    Limit,
    Market,
    Stop,
    StopLimit
};

enum class TimeInForce {
    GoodTillCancel, // GTC
    ImmediateOrCancel, // IOC
    FillOrKill // FOK
};

struct Order {
    int32_t orderId;
    int32_t traderId;
    std::string symbol;
    Side side;
    OrderType type;
    TimeInForce tif;
    double price;
    double stopPrice;
    int32_t quantity;
    int64_t timestamp;

    PriceLevel::iterator position_in_book;

    Order(int32_t orderId, int32_t traderId, std::string symbol, Side side, OrderType type, int32_t quantity, 
          double price = 0.0, double stopPrice = 0.0, TimeInForce tif = TimeInForce::GoodTillCancel, int64_t timestamp = 0)
        : orderId(orderId), traderId(traderId), symbol(std::move(symbol)), side(side), type(type), tif(tif), 
          price(price), stopPrice(stopPrice), quantity(quantity), timestamp(timestamp) {}
};

struct Trade {
    int32_t tradeId;
    int32_t aggressingOrderId;
    int32_t restingOrderId;
    std::string symbol;
    double price;
    int32_t quantity;
    int64_t timestamp;
};
