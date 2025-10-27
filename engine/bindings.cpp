#include <pybind11/pybind11.h>
#include <pybind11/stl.h> 
#include <chrono>
#include "OrderBook.h"
#include "Order.h"
#include <memory>

namespace py = pybind11;

// Helper function to create an Order from Python
std::unique_ptr<Order> make_order(int32_t orderId, int32_t traderId, std::string symbol, Side side, OrderType type, int32_t quantity, 
                                 double price, double stopPrice, TimeInForce tif) {
    int64_t timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(
               std::chrono::system_clock::now().time_since_epoch()
           ).count();
    return std::make_unique<Order>(orderId, traderId, std::move(symbol), side, type, quantity, price, stopPrice, tif, timestamp);
}

PYBIND11_MODULE(tradesim_engine, m) {
    m.doc() = "TradeSim C++ Matching Engine"; // Optional module docstring

    // --- Enums ---
    py::enum_<Side>(m, "Side")
        .value("Buy", Side::Buy)
        .value("Sell", Side::Sell)
        .export_values();

    py::enum_<OrderType>(m, "OrderType")
        .value("Limit", OrderType::Limit)
        .value("Market", OrderType::Market)
        .value("Stop", OrderType::Stop)
        .value("StopLimit", OrderType::StopLimit)
        .export_values();

    py::enum_<TimeInForce>(m, "TimeInForce")
        .value("GoodTillCancel", TimeInForce::GoodTillCancel)
        .value("ImmediateOrCancel", TimeInForce::ImmediateOrCancel)
        .value("FillOrKill", TimeInForce::FillOrKill)
        .export_values();

    // --- Structs ---

    // Register Order with full member access and unique_ptr ownership
    py::class_<Order, std::unique_ptr<Order>>(m, "Order")
        .def(py::init<int32_t, int32_t, std::string, Side, OrderType, int32_t, double, double, TimeInForce, int64_t>(),
            py::arg("orderId"), py::arg("traderId"), py::arg("symbol"), py::arg("side"),
            py::arg("type"), py::arg("quantity"), py::arg("price") = 0.0,
            py::arg("stopPrice") = 0.0, py::arg("tif") = TimeInForce::GoodTillCancel,
            py::arg("timestamp") = 0)
        .def_readonly("orderId", &Order::orderId)
        .def_readonly("traderId", &Order::traderId)
        .def_readonly("symbol", &Order::symbol)
        .def_readonly("side", &Order::side)
        .def_readonly("type", &Order::type)
        .def_readonly("tif", &Order::tif)
        .def_readonly("price", &Order::price)
        .def_readonly("stopPrice", &Order::stopPrice)
        .def_readonly("quantity", &Order::quantity)
        .def_readonly("timestamp", &Order::timestamp)
        .def("__repr__",
            [](const Order &o) {
                return "<Order " + std::to_string(o.orderId) + " " + 
                       (o.side == Side::Buy ? "BUY" : "SELL") + " " +
                       std::to_string(o.quantity) + " " + o.symbol + " @ " +
                       std::to_string(o.price) + ">";
            });

    // Expose the Trade struct
    py::class_<Trade>(m, "Trade")
        .def(py::init<>()) 
        .def_readonly("tradeId", &Trade::tradeId)
        .def_readonly("aggressingOrderId", &Trade::aggressingOrderId)
        .def_readonly("restingOrderId", &Trade::restingOrderId)
        .def_readonly("symbol", &Trade::symbol)
        .def_readonly("price", &Trade::price)
        .def_readonly("quantity", &Trade::quantity)
        .def_readonly("timestamp", &Trade::timestamp);

    // Factory function to create an Order - explicitly specify the return policy
    m.def("create_order", &make_order,
          py::arg("orderId"), py::arg("traderId"), py::arg("symbol"),
          py::arg("side"), py::arg("type"), py::arg("quantity"),
          py::arg("price") = 0.0, py::arg("stopPrice") = 0.0,
          py::arg("tif") = TimeInForce::GoodTillCancel,
          "A factory function to create a C++ Order object",
          py::return_value_policy::move); // Use move since we're returning a unique_ptr


    // --- Main OrderBook Class ---
    auto OrderBook_class = py::class_<OrderBook>(m, "OrderBook")
        .def(py::init<std::string>(), py::arg("symbol"))
        // Accept a Python Order object by reference, clone into a unique_ptr, then forward to C++ addOrder
        .def("addOrder", [](OrderBook &book, const Order &order) {
            auto ptr = std::make_unique<Order>(order.orderId, order.traderId, order.symbol, order.side,
                                               order.type, order.quantity, order.price, order.stopPrice,
                                               order.tif, order.timestamp);
            return book.addOrder(std::move(ptr));
        }, py::arg("order"), "Adds an order to the book and returns a list of trades made.")
        .def("cancelOrder", &OrderBook::cancelOrder, py::arg("orderId"))
        .def("getBids", &OrderBook::getBids,
             py::return_value_policy::copy)
        .def("getAsks", &OrderBook::getAsks,
             py::return_value_policy::copy);    // Helper functions for simplified book data - bind as methods on OrderBook
    OrderBook_class.def("get_bids_map", [](OrderBook &book) {
        std::map<double, int32_t> bids_summary;
        for (const auto& [price, level] : book.getBids()) {
            int32_t total_size = 0;
            for (const auto* order : level) {
                total_size += order->quantity;
            }
            if (total_size > 0) {
                bids_summary[price] = total_size;
            }
        }
        return bids_summary;
    }, "Returns a simple map of bid prices to total quantity.");

    OrderBook_class.def("get_asks_map", [](OrderBook &book) {
        std::map<double, int32_t> asks_summary;
        for (const auto& [price, level] : book.getAsks()) {
            int32_t total_size = 0;
            for (const auto* order : level) {
                total_size += order->quantity;
            }
            if (total_size > 0) {
                asks_summary[price] = total_size;
            }
        }
        return asks_summary;
    }, "Returns a simple map of ask prices to total quantity.");
}