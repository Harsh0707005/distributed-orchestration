from services.batch_listener import BatchListener

if __name__ == "__main__":
    listener = BatchListener()
    try:
        listener.running = True
        listener.listen()
    except KeyboardInterrupt:
        print("\nStopping batch listener...")
        listener.stop()

