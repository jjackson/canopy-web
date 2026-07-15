const DAYS = ["Sundays", "Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays"];

/** Friendly rendering for the common cron shapes; falls back to the raw
 * expression, which is always correct if not always pretty. Naming a cadence
 * wrongly would be worse than not naming it. This is a LABEL, never a schedule
 * computation — "when does this actually fire?" is always answered by the
 * server (see the editor's debounced preview). */
export function describeCron(cron: string, tz: string): string {
  const [min, hour, dom, mon, dow] = cron.trim().split(/\s+/);
  const time = `${hour.padStart(2, "0")}:${min.padStart(2, "0")}`;
  const zone = tz.split("/").pop()?.replace(/_/g, " ") ?? tz;
  if (dom === "*" && mon === "*" && /^[0-6]$/.test(dow)) {
    return `${DAYS[Number(dow)]} at ${time} · ${zone}`;
  }
  if (dow === "*" && mon === "*" && /^\d+$/.test(dom)) {
    return `Day ${dom} monthly at ${time} · ${zone}`;
  }
  if (dom === "*" && mon === "*" && dow === "*") return `Daily at ${time} · ${zone}`;
  return `${cron} · ${zone}`;
}

/** Coarse relative time — "in 2d", "3h ago". Deliberately not a full i18n
 * formatter: the table only needs to answer "soon or not?". */
export function relative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = new Date(iso).getTime() - Date.now();
  const days = Math.round(ms / 86_400_000);
  if (Math.abs(days) >= 1) return days > 0 ? `in ${days}d` : `${-days}d ago`;
  const hours = Math.round(ms / 3_600_000);
  if (Math.abs(hours) >= 1) return hours > 0 ? `in ${hours}h` : `${-hours}h ago`;
  return "now";
}
