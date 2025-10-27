import sys, os
# Prefer the freshly-built extension in build/lib if present
build_path = os.path.join(os.getcwd(), 'build', 'lib.win-amd64-cpython-313')
if os.path.isdir(build_path):
    sys.path.insert(0, build_path)

import tradesim_engine

print('pybind11 module:', tradesim_engine)

book = tradesim_engine.OrderBook('TEST')
print('Created OrderBook')

order = tradesim_engine.create_order(
    12345, 1, 'TEST', tradesim_engine.Side.Buy, tradesim_engine.OrderType.Limit, 100, 10.5
)
print('Created Order:', order.orderId, order.quantity, order.price)

trades = book.addOrder(order)
print('addOrder returned:', trades)
print('Done')
