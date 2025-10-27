# server.py
# v7: Integrated with C++ matching engine

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import time
import os
import threading
import sys
import random

# Ensure we use the latest built extension
build_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'build', 'lib.win-amd64-cpython-313')
if os.path.isdir(build_path):
    print(f"Using extension from: {build_path}")
    sys.path.insert(0, build_path)

# --- C++ Engine Import ---
try:
    import tradesim_engine
    print(f"Imported tradesim_engine from: {tradesim_engine.__file__}")
except ImportError:
    print("="*50)
    print("ERROR: Could not import C++ engine module.")
    print("Please run 'pip install pybind11' and then 'pip install .' in the root project directory.")
    print("="*50)
    exit(1)


# --- App Initialization ---
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)
# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', "postgresql://neondb_owner:npg_X0IewA1PDuor@ep-square-rice-a1s1ujv6-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
# Use threading mode for SocketIO to avoid eventlet/gevent issues
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


# --- Database Models ---
# This model is now just for *logging* trades that happen in the C++ engine
class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trade_id = db.Column(db.Integer) # From C++ engine, renamed from tradeId
    aggressing_order_id = db.Column(db.BigInteger)
    resting_order_id = db.Column(db.BigInteger)
    symbol = db.Column(db.String(32), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.BigInteger, nullable=False)

# The OrderBookEntry model is NO LONGER USED.
# The C++ engine is the single source of truth for the order book.


# --- C++ Engine & Global State ---
# We must use ONE global, stateful engine instance for each symbol.
# A lock is crucial to prevent two requests from modifying the order book
# at the exact same time (race condition).
engine_lock = threading.Lock()
order_books = {
    'RELIANCE': tradesim_engine.OrderBook("RELIANCE"),
    'AAPL': tradesim_engine.OrderBook("AAPL"),
    'MSFT': tradesim_engine.OrderBook("MSFT"),
    'GOOG': tradesim_engine.OrderBook("GOOG"),
    'AMZN': tradesim_engine.OrderBook("AMZN"),
    'META': tradesim_engine.OrderBook("META"),
    'TSLA': tradesim_engine.OrderBook("TSLA"),
}

# Simple counter for unique order IDs
current_order_id = int(time.time())
order_id_lock = threading.Lock()

def get_next_order_id():
    global current_order_id
    with order_id_lock:
        current_order_id += 1
        return current_order_id

# --- Helper function ---
def get_book_or_fail(symbol):
    """Gets the C++ order book for a symbol."""
    if symbol not in order_books:
        return None
    return order_books[symbol]

def get_current_orderbook_state(book):
    """Helper to get bids/asks from C++ and format for JSON."""
    with engine_lock:
        # Use the simple map functions we defined in bindings.cpp
        bids_map = book.get_bids_map()
        asks_map = book.get_asks_map()

    # Convert to list of [price, size] tuples for the frontend
    # Bids should be sorted high to low
    bids_list = sorted(bids_map.items(), key=lambda item: item[0], reverse=True)
    # Asks should be sorted low to high
    asks_list = sorted(asks_map.items(), key=lambda item: item[0])
    
    return {'bids': bids_list, 'asks': asks_list}


# --- Route to serve the frontend ---
@app.route('/')
def serve_frontend():
    return send_from_directory('../frontend', 'tradesim.html')


# --- REST API Endpoints (FIXED) ---
@app.route('/api/market_data')
def get_market_data():
    symbol = request.args.get('symbol', 'RELIANCE')
    # This mock data generation is fine for the chart
    base_prices = {
        'AAPL': 170.0, 'MSFT': 330.0, 'GOOG': 2800.0, 'AMZN': 3400.0,
        'META': 320.0, 'TSLA': 700.0, 'RELIANCE': 2850.0
    }
    price = base_prices.get(symbol, 100.0)
    data, current_time = [], int(time.time())
    for i in range(100):
        timestamp = current_time - (100 - i) * 60
        o, h, l, c = price + (i - 50) * 0.1 + random.uniform(-0.5, 0.5), 0, 0, 0
        h = max(o, c) + random.uniform(0, 2)
        l = min(o, c) - random.uniform(0, 2)
        c = o + random.uniform(-1, 1)
        data.append({"time": timestamp, "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)})
    return jsonify(data)

@app.route('/api/trades')
def get_trades():
    # *FIXED*: Added symbol filter and moved it *before* the return.
    symbol = request.args.get('symbol', 'RELIANCE')
    trades = Trade.query.filter_by(symbol=symbol).order_by(Trade.timestamp.desc()).all()
    result = [
        {
            'trade_id': t.trade_id, # Use the C++ trade_id
            'symbol': t.symbol,
            'price': t.price,
            'quantity': t.quantity,
            # This is a bit of a hack: determine side from aggressing order
            # In a real system, the aggressor's side determines the trade side
            # We'll just pass the aggressing order ID for now
            'side': 'N/A', # We'll fill this in the new /api/order
            'timestamp': t.timestamp
        } for t in trades
    ]
    return jsonify(result)

@app.route('/api/orderbook')
def get_orderbook():
    # *FIXED*: Now reads from C++ engine, not the DB.
    symbol = request.args.get('symbol', 'RELIANCE')
    book = get_book_or_fail(symbol)
    if not book:
        return jsonify({'error': 'Invalid symbol'}), 400
        
    return jsonify(get_current_orderbook_state(book))


@app.route('/api/order', methods=['POST'])
def place_order():
    # --- This is the new, integrated order logic ---
    order_data = request.json
    symbol = order_data.get('symbol')
    book = get_book_or_fail(symbol)
    if not book:
        return jsonify({'error': 'Invalid symbol'}), 400

    print(f"--- Received New Order: {order_data.get('side')} {order_data.get('quantity')} @ {order_data.get('price', 'Market')} for {symbol} ---")

    # 1. Convert Python dict to C++ Order
    order_type_str = order_data.get('type', 'limit')
    order_type = tradesim_engine.OrderType.Limit
    if order_type_str == 'market':
        order_type = tradesim_engine.OrderType.Market
        
    side_str = order_data.get('side', 'buy')
    side = tradesim_engine.Side.Buy if side_str.lower() == 'buy' else tradesim_engine.Side.Sell
    
    try:
        new_order = tradesim_engine.create_order(
            orderId=get_next_order_id(),
            traderId=1, # Hardcode trader ID for now
            symbol=symbol,
            side=side,
            type=order_type,
            quantity=int(order_data.get('quantity')),
            price=float(order_data.get('price', 0.0))
        )
    except Exception as e:
        print(f"Error creating C++ order: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 400

    # 2. Call the C++ engine. This is thread-safe.
    with engine_lock:
        print(f"Sending order {new_order.orderId} to C++ engine...")
        try:
            trades_made = book.addOrder(new_order)
        except Exception as e:
            print(f"C++ engine error: {e}")
            return jsonify({'status': 'error', 'message': f'Engine error: {e}'}), 500
        print(f"Engine processed order, {len(trades_made)} trades made.")

    # 3. Process results: Log trades and broadcast updates
    # We do this *outside* the lock to release the engine quickly
    if trades_made:
        for trade in trades_made:
            # Log trade to database using snake_case column names
            db_trade = Trade(
                trade_id=trade.tradeId,
                aggressing_order_id=trade.aggressingOrderId,
                resting_order_id=trade.restingOrderId,
                symbol=trade.symbol,
                price=trade.price,
                quantity=trade.quantity,
                timestamp=trade.timestamp
            )
            db.session.add(db_trade)
            
            # Broadcast trade to frontend (keep camelCase in JSON for frontend)
            trade_dict = {
                'trade_id': trade.tradeId,
                'symbol': trade.symbol,
                'price': trade.price,
                'quantity': trade.quantity,
                # The 'side' of the trade is the side of the aggressing order
                'side': 'Buy' if side == tradesim_engine.Side.Buy else 'Sell',
                'timestamp': trade.timestamp
            }
            socketio.emit('new_trade', trade_dict)
        
        db.session.commit()

    # 4. Broadcast the new order book state
    # This is critical so the UI updates after the order
    socketio.emit('order_book_update', get_current_orderbook_state(book))

    return jsonify({'status': 'success', 'message': 'Order processed', 'trades_made': len(trades_made)}), 200


# --- SocketIO Event Handlers (unchanged) ---
@socketio.on('connect')
def handle_connect(): 
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect(): 
    print('Client disconnected')


# --- Main Application Runner ---
def pre_populate_books():
    """Adds some initial orders to the C++ books to make them look alive."""
    print("Pre-populating C++ order books...")
    with engine_lock:
        # Example for AAPL
        aapl_book = get_book_or_fail("AAPL")
        if aapl_book:
            orders = [
                (tradesim_engine.Side.Buy, 100, 169.80),
                (tradesim_engine.Side.Buy, 150, 169.50),
                (tradesim_engine.Side.Sell, 120, 170.50),
                (tradesim_engine.Side.Sell, 180, 170.80),
            ]
            for side, qty, price in orders:
                order = tradesim_engine.create_order(
                    get_next_order_id(), 1, "AAPL", side, tradesim_engine.OrderType.Limit, qty, price
                )
                aapl_book.addOrder(order) # No trades expected, just adds resting orders
        
        # Example for RELIANCE
        rel_book = get_book_or_fail("RELIANCE")
        if rel_book:
            orders = [
                (tradesim_engine.Side.Buy, 100, 2850.50),
                (tradesim_engine.Side.Buy, 150, 2850.25),
                (tradesim_engine.Side.Sell, 120, 2851.00),
                (tradesim_engine.Side.Sell, 180, 2851.25),
            ]
            for side, qty, price in orders:
                order = tradesim_engine.create_order(
                    get_next_order_id(), 1, "RELIANCE", side, tradesim_engine.OrderType.Limit, qty, price
                )
                rel_book.addOrder(order)
    print("C++ order books pre-populated.")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print('Database tables created or already exist.')
        # *REMOVED* old DB-based order book population
        
    pre_populate_books()
    
    print(">>> Starting TradeSim Unified Server on http://12_7.0.0.1:5000")
    print(">>> Open this URL in your browser to launch the application.")
    socketio.run(app, host='127.0.0.1', port=5000)