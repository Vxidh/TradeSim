#pragma once

#include <string>
#include <utility>
#include <cstdint> 

enum class Side {
    Buy,
    Sell
};

enum class OrderType {
    Limit,
    Market
};

enum class TimeInForce {
    GoodTillCancel,
    FillOrKill,
    GoodForDay
};

struct Order {
    int32_t orderId;
    int32_t traderId;
    std::string symbol;
    Side side;
    OrderType type;
    TimeInForce tif;
    double price;
    int32_t quantity;
    int64_t timestamp;

    Order() = default;

    Order(int32_t orderId, int32_t traderId, std::string symbol, Side side, OrderType type, TimeInForce tif, double price, int32_t quantity, int64_t timestamp)
        : orderId(orderId), traderId(traderId), symbol(std::move(symbol)), side(side), type(type), tif(tif), price(price), quantity(quantity), timestamp(timestamp) {}
};