import socket
import threading
import sys

HOST = "127.0.0.1"
PORT = 5050


def receive_messages(sock):
    while True:
        try:
            data = sock.recv(1024)
            if not data:
                print("\n[System] Server closed the connection.")
                break
            print("\r" + data.decode("utf-8").strip())
            print("You: ", end="", flush=True)
        except OSError:
            break


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, PORT))
    except ConnectionRefusedError:
        print("Could not connect. Is server.py running?")
        sys.exit(1)

    prompt = sock.recv(1024).decode("utf-8")
    username = input(prompt).strip() or "Anonymous"
    sock.sendall(username.encode("utf-8"))

    threading.Thread(target=receive_messages, args=(sock,), daemon=True).start()

    print(f"Connected as {username}. Type '/quit' to exit.\n")
    try:
        while True:
            msg = input("You: ")
            if msg.strip().lower() == "/quit":
                sock.sendall(msg.encode("utf-8"))
                break
            if msg.strip():
                sock.sendall(msg.encode("utf-8"))
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        sock.close()
        print("Disconnected.")


if __name__ == "__main__":
    main()
