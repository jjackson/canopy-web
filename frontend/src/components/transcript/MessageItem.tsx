import type { SessionMessage } from "../../api/sessions";

interface Props {
  message: SessionMessage;
}

/** Renders one transcript turn. Tool calls collapse into <details>. */
export function MessageItem({ message }: Props) {
  if (message.role === "tool_use") {
    const name = String(
      (message.content as { name?: unknown })?.name ?? "unknown",
    );
    return (
      <details className="my-1 rounded border border-zinc-200 bg-zinc-50 p-2 text-sm">
        <summary className="cursor-pointer text-zinc-500">
          tool_use: {name}
        </summary>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs text-zinc-500">
          {JSON.stringify(message.content, null, 2)}
        </pre>
      </details>
    );
  }

  if (message.role === "tool_result") {
    return (
      <details className="my-1 rounded border border-zinc-200 bg-zinc-50 p-2 text-sm">
        <summary className="cursor-pointer text-zinc-500">tool_result</summary>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-xs text-zinc-500">
          {message.plaintext}
        </pre>
      </details>
    );
  }

  const isUser = message.role === "user";
  const bubble = isUser
    ? "ml-auto bg-zinc-900 text-zinc-50"
    : "mr-auto bg-zinc-100 text-zinc-900";
  return (
    <div className={`my-2 max-w-[80%] rounded-2xl px-4 py-2 ${bubble}`}>
      <div className="whitespace-pre-wrap break-words text-sm">
        {message.plaintext}
      </div>
    </div>
  );
}
