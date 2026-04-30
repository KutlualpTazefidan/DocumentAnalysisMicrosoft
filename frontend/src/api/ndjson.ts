export async function* streamNdjson<T>(response: Response): AsyncIterable<T> {
  if (!response.body) {
    throw new Error("response has no body to stream");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        if (buffer.trim()) {
          yield JSON.parse(buffer) as T;
        }
        return;
      }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.trim()) yield JSON.parse(line) as T;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
