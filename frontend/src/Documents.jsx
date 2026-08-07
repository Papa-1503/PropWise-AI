import { useState, useEffect, useCallback } from "react";
import { FileText, Download, PenLine } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import EmptyState from "./EmptyState";

/**
 * Documents — staff can create a document for a tenant (title + content);
 * the tenant can view, e-sign (typed name, timestamped), and download a
 * PDF. See routers/documents.py for the legal-content caveat: this app
 * does not generate lease language, only the workflow around it.
 */
export default function Documents() {
  const { user } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ tenantEmail: "", title: "", content: "" });
  const [creating, setCreating] = useState(false);

  const [signingId, setSigningId] = useState(null);
  const [signName, setSignName] = useState("");
  const [signing, setSigning] = useState(false);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/documents`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      if (!res.ok) throw new Error("Couldn't load documents.");
      const data = await res.json();
      setDocuments(data.documents || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  async function handleCreate(e) {
    e.preventDefault();
    setCreating(true);
    try {
      const res = await fetch(`${API_BASE}/documents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify(form),
      });
      if (!res.ok) throw new Error("Couldn't create document.");
      setForm({ tenantEmail: "", title: "", content: "" });
      setShowCreate(false);
      fetchDocuments();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }

  async function handleSign(docId) {
    setSigning(true);
    try {
      const res = await fetch(`${API_BASE}/documents/${docId}/sign`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify({ signedByName: signName }),
      });
      if (!res.ok) throw new Error("Couldn't sign document.");
      setSigningId(null);
      setSignName("");
      fetchDocuments();
    } catch (err) {
      setError(err.message);
    } finally {
      setSigning(false);
    }
  }

  function downloadPdf(docId) {
    fetch(`${API_BASE}/documents/${docId}/pdf`, {
      headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
    })
      .then((res) => res.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `document_${docId}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      });
  }

  return (
    <div className="p-5">
      <div className="flex items-center
