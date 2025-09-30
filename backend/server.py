# server.py
# v6: Final, definitive version. All complex async dependencies (gevent, eventlet)
# have been removed to guarantee stability and prevent compatibility errors.

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
import time
import random

# --- App Initialization ---
app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)
# Use threading mode for SocketIO to avoid eventlet/gevent issues
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# --- In-Memory Database Simulation (unchanged) ---
mock_trades = [
    {'trade_id': 1, 'symbol': 'RELIANCE', 'price': 2850.50, 'quantity': 10, 'side': 'Buy', 'timestamp': int(time.time() * 1000) - 5000},
    {'trade_id': 2, 'symbol': 'RELIANCE', 'price': 2851.00, 'quantity': 5, 'side': 'Sell', 'timestamp': int(time.time() * 1000) - 3000},
]
bids = {2850.50: 100, 2850.25: 150, 2850.00: 200}
asks = {2851.00: 120, 2851.25: 180, 2851.50: 250}

def generate_market_data():
    data, price, current_time = [], 2800.0, int(time.time())
    for i in range(100):
        timestamp = current_time - (100 - i) * 60
        o, h, l, c = price + random.uniform(-5, 5), 0, 0, 0
        h, l = o + random.uniform(0, 5), o - random.uniform(0, 5)
        c = random.uniform(l, h)
        data.append({"time": timestamp, "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)})
        price = c
    return data
market_data = generate_market_data()


# --- Route to serve the frontend ---
@app.route('/')
def serve_frontend():
    return send_from_directory('../frontend', 'tradesim.html')


# --- REST API Endpoints (unchanged) ---
@app.route('/api/market_data')
def get_market_data(): return jsonify(market_data)

@app.route('/api/trades')
def get_trades(): return jsonify(sorted(mock_trades, key=lambda x: x['timestamp'], reverse=True))

@app.route('/api/orderbook')
def get_orderbook():
    return jsonify({'bids': sorted(bids.items(), key=lambda x: x[0], reverse=True), 'asks': sorted(asks.items())})

@app.route('/api/order', methods=['POST'])
def place_order():
    order = request.json
    print(f"--- Received New Order: {order.get('side')} {order.get('quantity')} @ {order.get('price', 'Market')} ---")
    
    trade_price = market_data[-1]['close'] + random.uniform(-0.5, 0.5)
    new_trade = {
        'trade_id': len(mock_trades) + 1, 'symbol': order.get('symbol'),
        'price': round(trade_price, 2), 'quantity': int(order.get('quantity')),
        'side': order.get('side'), 'timestamp': int(time.time() * 1000)
    }
    mock_trades.append(new_trade)
    socketio.emit('new_trade', new_trade)

    if order.get('side') == 'Buy' and asks:
        best_ask = list(asks.keys())[0]
        asks[best_ask] = max(0, asks[best_ask] - int(order.get('quantity')))
        if asks[best_ask] == 0: del asks[best_ask]
    elif order.get('side') == 'Sell' and bids:
        best_bid = list(bids.keys())[0]
        bids[best_bid] = max(0, bids[best_bid] - int(order.get('quantity')))
        if bids[best_bid] == 0: del bids[best_bid]

    socketio.emit('order_book_update', {'bids': sorted(bids.items(), key=lambda x: x[0], reverse=True), 'asks': sorted(asks.items())})
    return jsonify({'status': 'success', 'message': 'Order received'}), 200


# --- SocketIO Event Handlers (unchanged) ---
@socketio.on('connect')
def handle_connect(): print('Client connected')

@socketio.on('disconnect')
def handle_disconnect(): print('Client disconnected')


if __name__ == '__main__':
    print(">>> Starting TradeSim Unified Server on http://127.0.0.1:5000")
    print(">>> Open this URL in your browser to launch the application.")
    socketio.run(app, host='127.0.0.1', port=5000)