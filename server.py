import socket
import threading
import datetime

HOST = "127.0.0.1"
PORT = 5050

clients = {}        
lock = threading.Lock()


def timestamp():
    return datetime.datetime.now().strftime("%H:%M")


def broadcast(message, exclude_conn=None):
    """Send a line to every connected client except (optionally) the sender."""
    with lock:
        dead = []
        for conn in clients:
            if conn is exclude_conn:
                continue
            try:
                conn.sendall((message + "\n").encode("utf-8"))
            except OSError:
                dead.append(conn)
        for conn in dead:
            clients.pop(conn, None)


def handle_client(conn, addr):
    username = None
    try:
        conn.sendall("Enter your username: ".encode("utf-8"))
        raw = conn.recv(1024)
        if not raw:
            return
        username = raw.decode("utf-8").strip() or f"User{addr[1]}"

        with lock:
            clients[conn] = username

        print(f"[+] {username} connected from {addr}")
        broadcast(f"*** {username} has joined the chat ***")

        while True:
            raw = conn.recv(1024)
            if not raw:
                break  # client closed the socket -> disconnect
            text = raw.decode("utf-8").strip()
            if not text:
                continue
            if text.lower() == "/quit":
                break
            formatted = f"[{timestamp()}] {username}: {text}"
            print(formatted)
            broadcast(formatted, exclude_conn=conn)

    except (ConnectionResetError, ConnectionAbortedError):
        pass
    finally:
        with lock:
            clients.pop(conn, None)
        if username:
            print(f"[-] {username} disconnected")
            broadcast(f"*** {username} has left the chat ***")
        conn.close()


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(2)  # beginner tier is designed for exactly two users
    print(f"Chat server listening on {HOST}:{PORT} ... (Ctrl+C to stop)")

    try:
        while True:
            conn, addr = server.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nServer shutting down...")
    finally:
        server.close()


if __name__ == "__main__":
    main()
