/** Colour labels for clients and coordinators, like the colour-coded dropdowns of the old Google Sheet. */

// hue per client, matching the old sheet where it had a colour; others get a stable hue from their name
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

function style(h: number, sat = 70) {
  return {
    color: `hsl(${h} ${sat}% 78%)`,
    background: `hsl(${h} ${sat}% 55% / 0.14)`,
    borderColor: `hsl(${h} ${sat}% 60% / 0.35)`,
  } as React.CSSProperties;
}

export function ClientChip({ name }: { name: string | null | undefined }) {
  if (!name) return <>—</>;
  const h = CLIENT_HUE[name] ?? hueOf(name);
  return <span className="chip" style={style(h, name === "PANDA" ? 0 : 70)}><i style={{ background: `hsl(${h} ${name === "PANDA" ? 0 : 75}% 62%)` }} />{name}</span>;
}

export function OwnerChip({ initials }: { initials: string | null | undefined }) {
  if (!initials) return <>—</>;
  const h = OWNER_HUE[initials] ?? hueOf(initials);
  return <span className="chip owner" style={style(h, 75)}>{initials}</span>;
}
