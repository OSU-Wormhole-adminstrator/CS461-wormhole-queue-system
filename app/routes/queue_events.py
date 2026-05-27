# app/routes/queue_events.py
"""
SocketIO events for real-time queue updates.
Handles broadcasting ticket updates to connected clients.
"""

from datetime import datetime, timezone

from flask import request

from app import socketio
from app.models import Box, Ticket
from app.time_utils import format_pacific, serialize_datetime


@socketio.on("connect", namespace="/queue")
def handle_queue_connect():
    """Handle client connection to queue namespace."""
    print("Client connected to /queue")


@socketio.on("disconnect", namespace="/queue")
def handle_queue_disconnect():
    """Handle client disconnect from queue namespace."""
    print("Client disconnected from /queue")


def broadcast_ticket_update(ticket_id):
    """
    Broadcast a ticket update to all connected clients on the queue namespace.
    Called when a new ticket is created or updated.
    """
    try:
        t = Ticket.query.get(ticket_id)
        if t:
            ticket_data = {
                "id": t.id,
                "student_name": t.student_name,
                "table": t.table,
                "physics_course": t.physics_course,
                "created_at": serialize_datetime(t.created_at),
                "created_at_local": format_pacific(
                    t.created_at, "%Y-%m-%d %H:%M:%S %Z"
                ),
                "status": t.status,
            }
            socketio.emit("new_ticket", ticket_data, namespace="/queue")
            print(f"Broadcasted ticket update for ticket ID {ticket_id}")
    except Exception as e:
        print(f"Error broadcasting ticket update: {e}")


def broadcast_queue_refresh():
    """
    Broadcast a refresh signal to all connected clients.
    Triggers the client to refetch the queue.
    """
    socketio.emit("queue_refresh", {}, namespace="/queue")


@socketio.on("connect", namespace="/hardware")
def handle_hardware_connect():
    """Handle client connection to the hardware namespace."""
    print("Client connected to /hardware")
    # Send the current hardware state immediately to the connecting client
    try:
        boxes = Box.query.order_by(Box.name).all()
        most_recent = max((box.last_seen for box in boxes), default=datetime.now(timezone.utc))
        payload = {
            "boxes": [box.to_dict() for box in boxes],
            "last_update": format_pacific(most_recent, "%Y-%m-%d %H:%M:%S %Z"),
        }
        # Emit only to the connecting client
        socketio.emit("hardware_update", payload, namespace="/hardware", room=request.sid)
    except Exception as e:
        print(f"Error sending initial hardware state: {e}")


@socketio.on("disconnect", namespace="/hardware")
def handle_hardware_disconnect():
    """Handle client disconnect from the hardware namespace."""
    print("Client disconnected from /hardware")


def broadcast_hardware_update():
    """
    Broadcast the current hardware box list to all connected hardware clients.
    """
    try:
        boxes = Box.query.order_by(Box.name).all()
        most_recent = max(
            (box.last_seen for box in boxes), default=datetime.now(timezone.utc)
        )
        payload = {
            "boxes": [box.to_dict() for box in boxes],
            "last_update": format_pacific(most_recent, "%Y-%m-%d %H:%M:%S %Z"),
        }
        socketio.emit("hardware_update", payload, namespace="/hardware")
        print(f"Broadcasted hardware update for {len(boxes)} boxes")
    except Exception as e:
        print(f"Error broadcasting hardware update: {e}")
