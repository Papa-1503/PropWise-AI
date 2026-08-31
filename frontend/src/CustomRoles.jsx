import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import EmptyState from "./EmptyState";
import { Shield, Plus, X, Trash2 } from "lucide-react";
import { API_BASE } from "./config";

const PERMISSION_CHOICES = ["leasing", "maintenance", "finance", "communications", "staff_management", "reports"];

export default function CustomRoles() {
  const [roles, setRoles] = useState([]);
  const [staffList, setStaffList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const { authFetch } = useAuth();

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rolesRes, staffRes] = await Promise.all([
        authFetch(`${API_BASE}/custom-roles`),
        authFetch(`${API_BASE}/staff`),
      ]);
      if (!rolesRes.ok) throw new Error("Couldn't load custom roles.");
      const rolesData = await rolesRes.json();
      const staffData = await staffRes.json().catch(() => ({ staff: [] }));
      setRoles(rolesData.roles || []);
      setStaffList(staffData.staff || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  async function handleDelete(roleId) {
    if (!window.confirm("Delete this role? Staff assigned to it will need to be reassigned.")) return;
    const res = await authFetch(`${API_BASE}/custom-roles/${roleId}`, { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      alert(data.detail || "Couldn't delete this role.");
      return;
    }
    fetchData();
  }

  async function handleAssign(userId, customRoleId) {
    const res = await authFetch(`${API_BASE}/custom-roles/staff/${userId}/assign`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customRoleId: customRoleId || null }),
    });
    if (res.ok) fetchData();
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Roles & Permissions</h2>
        <button
          onClick={() => setShowNew(true)}
          className="flex items-center gap-1.5 text-sm font-semibold bg-slate-900 text-white px-3 py-1.5 rounded-lg hover:bg-slate-800"
        >
          <Plus size={14} /> New role
        </button>
      </div>

      <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg p-3 mb-3">
        Staff with no role assigned below keep full access, same as today. A role only ever scopes access down for whoever is explicitly assigned one.
      </p>

      {loading && <div className="text-sm text-slate-500">Loading...</div>}
      {error && <div className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-3" role="alert">{error}</div>}

      {!loading && !error && roles.length === 0 && (
        <EmptyState icon={Shield} title="No custom roles yet" subtitle="Create one to scope a staff member's access to specific areas." />
      )}

      {!loading && !error && roles.length > 0 && (
        <div className="space-y-2 mb-4">
          {roles.map((r) => (
            <div key={r.id} className="bg-white border border-slate-200 rounded-lg p-3 flex items-start justify-between">
              <div>
                <p className="text-sm font-medium">{r.name}</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {r.permissions.map((p) => (
                    <span key={p} className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600">
                      {p.replace("_", " ")}
                    </span>
                  ))}
                </div>
              </div>
              <button onClick={() => handleDelete(r.id)} className="text-slate-300 hover:text-rose-500">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      {!loading && !error && staffList.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold mb-2">Assign roles to staff</h3>
          <div className="space-y-2">
            {staffList.map((s) => (
              <div key={s.id} className="flex items-center justify-between">
                <span className="text-sm">{s.name || s.email}</span>
                <select
                  value={s.customRoleId || ""}
                  onChange={(e) => handleAssign(s.id, e.target.value)}
                  className="text-xs border border-slate-200 rounded-lg px-2 py-1"
                >
                  <option value="">Full access (no role)</option>
                  {roles.map((r) => (
                    <option key={r.id} value={r.id}>{r.name}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </div>
      )}

      {showNew && <NewRoleModal onClose={() => setShowNew(false)} onSaved={fetchData} />}
    </div>
  );
}

function NewRoleModal({ onClose, onSaved }) {
  const [name, setName] = useState("");
  const [permissions, setPermissions] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const { authFetch } = useAuth();

  function togglePermission(p) {
    setPermissions((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_BASE}/custom-roles`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, permissions }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Couldn't save the role.");
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-30 p-4">
      <div className="bg-white rounded-xl p-5 w-full max-w-sm">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold">New role</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>
        {error && <p className="text-sm text-rose-600 mb-2" role="alert">{error}</p>}
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Role name (e.g. Leasing Agent)"
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm mb-3"
        />
        <p className="text-xs font-medium text-slate-600 mb-1.5">Permissions</p>
        <div className="space-y-1.5 mb-3">
          {PERMISSION_CHOICES.map((p) => (
            <label key={p} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={permissions.includes(p)} onChange={() => togglePermission(p)} />
              {p.replace("_", " ")}
            </label>
          ))}
        </div>
        <button
          onClick={handleSave}
          disabled={saving || !name || permissions.length === 0}
          className="w-full bg-slate-900 text-white rounded-lg py-2 text-sm font-semibold hover:bg-slate-800 disabled:opacity-50"
        >
          {saving ? "Saving..." : "Save role"}
        </button>
      </div>
    </div>
  );
}
