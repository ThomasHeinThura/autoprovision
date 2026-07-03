// Small presentational helpers shared across pages (charco theme).

export const STATUS: Record<string, { label: string; cls: string }> = {
  todo: { label: "To Do", cls: "st-todo" },
  prog: { label: "In Progress", cls: "st-prog" },
  wait: { label: "Waiting", cls: "st-wait" },
  done: { label: "Resolved", cls: "st-done" },
};
export const COLS = ["todo", "prog", "wait", "done"];

export function Chip({ s }: { s: string }) {
  const st = STATUS[s] ?? STATUS.todo;
  return (
    <span className={"chip " + st.cls}>
      <span className="tick" />
      {st.label}
    </span>
  );
}

export function Pri({ p }: { p: string }) {
  return (
    <span className={"pri " + p}>
      <span className="pdot" />
      {p ? p[0].toUpperCase() + p.slice(1) : "—"}
    </span>
  );
}

export function TypeTag({ t }: { t: string }) {
  return <span className={"type-tag type-" + t}>{(t || "").toUpperCase()}</span>;
}

const AVPAL = ["#2f9e6a", "#d98f26", "#9a6dc9", "#4f93d6", "#c56b3f", "#3a8f8a", "#c65a7a"];
export function initials(name?: string) {
  return (name || "?")
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}
export function Avatar({ name, size = 24 }: { name?: string; size?: number }) {
  const style: any = { width: size, height: size, fontSize: size * 0.4 };
  if (!name) return <span className="avatar" style={{ ...style, background: "var(--surface-3)", color: "var(--faint)" }}>–</span>;
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return <span className="avatar" style={{ ...style, background: AVPAL[h % AVPAL.length], color: "#fff" }} title={name}>{initials(name)}</span>;
}

export function StatTile({ n, label, color }: { n: any; label: string; color?: string }) {
  return (
    <div className="card stat" style={{ borderTop: `2px solid ${color || "var(--border-strong)"}` }}>
      <div className="n">{n}</div>
      <div className="l">{label}</div>
    </div>
  );
}
