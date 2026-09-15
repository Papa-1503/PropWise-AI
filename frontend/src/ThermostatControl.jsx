import { useState, useEffect } from "react";
import { Thermometer, Flame, Snowflake, Power, Leaf, RefreshCw } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";

/**
 * ThermostatControl
 *
 * Real, live Seam thermostat status + remote HVAC control for one
 * unit — the frontend for backend/routers/thermostats.py. Shown
 * inline within EditUnitModal once a unit has a real
 * seamThermostatDeviceId set. Returns nothing (renders no UI at all)
 * when no device is linked yet, rather than showing empty/disabled
 * controls for a feature that isn't connected.
 *
 * Genuine, real value: staff can set a vacant unit's thermostat to an
 * energy-saving mode between tenants, or prep a unit's climate ahead
 * of a move-in, without a physical visit — the same "remote control,
 * no truck roll" value smart locks already provide for access.
 */

const MODES = [
  { value: "heat", label: "Heat", icon: Flame },
  { value: "cool", label: "Cool", icon: Snowflake },
  { value: "heat_cool", label: "Auto", icon: Thermometer },
  { value: "eco", label: "Eco", icon: Leaf },
  { value: "off", label: "Off", icon: Power },
];

export default function ThermostatControl({ propertyId, unitId, deviceId }) {
  const [device, setDevice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notConfigured, setNotConfigured] = useState(false);
  const [applying, setApplying] = useState(null); // which mode is currently being applied
  const [heatSetPoint, setHeatSetPoint] = useState(68);
  const [coolSetPoint, setCoolSetPoint] = useState(72);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  async function fetchStatus() {
    if (!deviceId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/thermostats/${propertyId}/units/${unitId}`);
      if (res.status === 501) {
        setNotConfigured(true);
        return;
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't reach this thermostat.");
      setDevice(data.device);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId]);

  async function applyMode(mode) {
    setApplying(mode);
    setError(null);
    try {
      const body = { hvacMode: mode };
      if (mode === "heat" || mode === "heat_cool") body.heatingSetPointFahrenheit = Number(heatSetPoint);
      if (mode === "cool" || mode === "heat_cool") body.coolingSetPointFahrenheit = Number(coolSetPoint);

      const res = await authFetch(`${API_BASE}/thermostats/${propertyId}/units/${unitId}/set-mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't apply that mode.");
      await fetchStatus();
    } catch (err) {
      setError(err.message);
    } finally {
      setApplying(null);
    }
  }

  if (!deviceId) return null;

  if (notConfigured) {
    return (
      <p className="text-xs text-slate-400 italic mt-3">
        Thermostat control isn't set up for this organization yet.
      </p>
    );
  }

  return (
    <div className="mt-4 pt-4 border-t border-slate-100">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-slate-600 flex items-center gap-1.5">
          <Thermometer size={13} /> Thermostat
        </h4>
        <button onClick={fetchStatus} className="text-slate-400 hover:text-slate-600" title="Refresh">
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {error && <p role="alert" className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded px-2 py-1.5 mb-2">{error}</p>}

      {device && (
        <p className="text-xs text-slate-500 mb-2">
          Current: {device.current_temperature_fahrenheit != null ? `${device.current_temperature_fahrenheit}°F` : "—"}
          {device.hvac_mode_setting ? ` · ${device.hvac_mode_setting}` : ""}
        </p>
      )}

      <div className="flex gap-1.5 mb-2 flex-wrap">
        {MODES.map((m) => {
          const Icon = m.icon;
          return (
            <button
              key={m.value}
              onClick={() => applyMode(m.value)}
              disabled={applying !== null}
              className="flex items-center gap-1 text-xs border border-slate-200 rounded-full px-2.5 py-1 hover:bg-slate-50 disabled:opacity-50"
            >
              <Icon size={12} />
              {applying === m.value ? "…" : m.label}
            </button>
          );
        })}
      </div>

      <div className="flex gap-3 text-xs">
        <label className="flex items-center gap-1 text-slate-500">
          Heat to
          <input
            type="number" value={heatSetPoint} onChange={(e) => setHeatSetPoint(e.target.value)}
            className="w-14 border border-slate-200 rounded px-1.5 py-0.5"
          />°F
        </label>
        <label className="flex items-center gap-1 text-slate-500">
          Cool to
          <input
            type="number" value={coolSetPoint} onChange={(e) => setCoolSetPoint(e.target.value)}
            className="w-14 border border-slate-200 rounded px-1.5 py-0.5"
          />°F
        </label>
      </div>
    </div>
  );
}
