interface Props {
  connected: boolean;
}

/**
 * WS connection chip — "Connected" (success) or "Reconnecting…" (warning).
 * The ace CLI-auth variant is stripped; the kit only knows about the socket.
 */
export function ConnectionStatus({ connected }: Props) {
  if (!connected) {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-xs text-warning"
        title="Trying to reconnect to the chat server."
      >
        <span className="h-2 w-2 animate-pulse rounded-full bg-warning" />
        Reconnecting…
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-success/40 bg-success/10 px-2 py-0.5 text-xs text-success"
      title="Connected."
    >
      <span className="h-2 w-2 rounded-full bg-success" />
      Connected
    </span>
  );
}
