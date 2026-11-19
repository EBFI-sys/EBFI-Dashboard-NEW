/** Colour labels for clients and coordinators, like the colour-coded dropdowns of the old Google Sheet.
 *  Colours are chosen in «Справочники → Клиенты» and «Пользователи»; until then a default is used. */
import { useRef_ } from "../refs";

// defaults matching the old sheet where it had a colour; others get a stable colour from their name
const CLIENT_HUE: Record<string, number> = {
  "TUV Rheinland": 48, "TUV Rheinland LT": 48, "TUV NORD": 220, "LRQA": 28, "LRQA Singapore": 170, "BV Singapore": 265,
  "BV Indonesia": 200, "BV USA": 140, "BV": 250, "TUV Rheinland Qatar": 195, "TUV Rheinland Oman": 330, "ISPEX": 85,
  "PANDA": 0, "TUV AT": 15, "Qualcon": 300, "Applus": 350, "APPLUS Indonesia": 350, "IRClass": 180, "TUV TPS": 100,
};
const OWNER_HUE: Record<string, number> = { LM: 215, LR: 275, SV: 150, MB: 35 };

function hueOf(name: string) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

/** hsl -> #rrggbb, so a default can be shown in the colour picker */
function hex(h: number, s: number, l: number) {
  s /= 100; l /= 100;
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return "#" + [f(0), f(8), f(4)].map((x) => Math.round(x * 255).toString(16).padStart(2, "0")).join("");
}

export const defaultClientColor = (name: string) => (name === "PANDA" ? "#9aa3b2" : hex(CLIENT_HUE[name] ?? hueOf(name), 75, 60));
export const defaultOwnerColor = (initials: string) => hex(OWNER_HUE[initials] ?? hueOf(initials), 75, 62);

export function chipStyle(c: string): React.CSSProperties {
  return {
    color: `color-mix(in srgb, ${c} 58%, var(--chip-mix))`,
    background: `color-mix(in srgb, ${c} 16%, transparent)`,
    borderColor: `color-mix(in srgb, ${c} 45%, transparent)`,
  };
}

export function ClientChip({ name, color }: { name: string | null | undefined; color?: string | null }) {
  const clients = useRef_("clients");
  if (!name) return <>—</>;
  const c = color || clients.find((x) => x.name === name)?.color || defaultClientColor(name);
  return <span className="chip" style={chipStyle(c)}><i style={{ background: c }} />{name}</span>;
}

export function OwnerChip({ initials, color }: { initials: string | null | undefined; color?: string | null }) {
  const users = useRef_("users");
  if (!initials) return <>—</>;
  const c = color || users.find((x) => x.initials === initials)?.color || defaultOwnerColor(initials);
  return <span className="chip owner" style={chipStyle(c)}>{initials}</span>;
}

/** Colour picker with a ready palette, a free choice and «по умолчанию». */
const PALETTE = ["#f5c542", "#f59e42", "#ef6b6b", "#ec6fb3", "#a77bf3", "#6f7cf5", "#4c9ff0", "#3cc6e0", "#34d399", "#9bd34a", "#9aa3b2"];

export function ColorInput({ value, onChange, fallback }: { value: string | null; onChange: (v: string | null) => void; fallback: string }) {
  const cur = value || fallback;
  return (
    <div className="color-input">
      <div className="swatches">
        {PALETTE.map((c) => (
          <button key={c} type="button" className={"swatch" + (value === c ? " on" : "")} style={{ background: c }} title={c} aria-label={`Цвет ${c}`} onClick={() => onChange(c)} />
        ))}
        <label className="swatch custom" title="Свой цвет" style={{ background: cur }}>
          <input type="color" value={cur} onChange={(e) => onChange(e.target.value)} aria-label="Свой цвет" />+
        </label>
      </div>
      <div className="color-row">
        <span className="chip" style={chipStyle(cur)}><i style={{ background: cur }} />Пример</span>
        {value && <button type="button" className="btn small ghost" onClick={() => onChange(null)}>По умолчанию</button>}
      </div>
    </div>
  );
}
