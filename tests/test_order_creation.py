import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import tradesim_engine

def test_create_order():
    """Test creating an order and inspecting its properties"""
    try:
        order = tradesim_engine.create_order(
            orderId=12345,
            traderId=1,
            symbol="TEST",
            side=tradesim_engine.Side.Buy,
            type=tradesim_engine.OrderType.Limit,
            quantity=100,
            price=10.5
        )
        print("Successfully created order:", order)
        print("Order fields:")
        print(f"  orderId: {order.orderId}")
        print(f"  symbol: {order.symbol}")
        print(f"  side: {order.side}")
        print(f"  quantity: {order.quantity}")
        print(f"  price: {order.price}")
        return order
    except Exception as e:
        print(f"Error creating order: {e}")
        raise

def test_add_to_book(order):
    """Test adding the order to an order book"""
    try:
        book = tradesim_engine.OrderBook("TEST")
        print("\nCreated order book for TEST")
        
        trades = book.addOrder(order)
        print(f"Successfully added order to book. Trades made: {trades}")
        return book
    except Exception as e:
        print(f"Error adding to book: {e}")
        raise

if __name__ == '__main__':
    print("Testing order creation and book operations...")
    order = test_create_order()
    if order:
        test_add_to_book(order)
    print("Done.")