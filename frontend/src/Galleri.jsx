import { useState, useEffect, useCallback } from "react";
import { Image as ImageIcon, Trash2, Upload } from "lucide-react";
import { useAuth } from "./AuthContext";
import { API_BASE } from "./config";
import EmptyState from "./EmptyState";

/**
 * Property-wide photo gallery — units, amenities, common areas. Staff
 * can upload/delete; tenants can view.
 */
export default function Gallery() {
  const { user } = useAuth();
  const [photos, setPhotos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [caption, setCaption] = useState("");

  const fetchPhotos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/gallery/${user.propertyId}/photos`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      if (!res.ok) throw new Error("Couldn't load gallery.");
      const data = await res.json();
      setPhotos(data.photos || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [user.propertyId]);

  useEffect(() => {
    fetchPhotos();
  }, [fetchPhotos]);

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("caption", caption);
      const res = await fetch(`${API_BASE}/gallery/${user.propertyId}/photos`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
        body: formData,
      });
      if (!res.ok) throw new Error("Upload failed.");
      setCaption("");
      fetchPhotos();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function handleDelete(photoId) {
    try {
      const res = await fetch(`${API_BASE}/gallery/photos/${photoId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      if (!res.ok) throw new Error("Couldn't delete photo.");
      setPhotos((p) => p.filter((ph) => ph._id !== photoId));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="p-5">
      <h1 className="text-2xl font-semibold mb-1">Gallery</h1>
      <p className="text-sm text-slate-500 mb-5">Photos of units, amenities, and common areas.</p>

      {user.role === "staff" && (
        <div className="bg-white border border-slate-200 rounded-xl p-4 mb-5 flex items-center gap-3">
          <input
            type="text" placeholder="Caption (optional)" value={caption}
            onChange={(e) => setCaption(e.target.value)}
            className="flex-1 text-sm border border-slate-200 rounded-md px-3 py-2"
          />
          <label className="flex items-center gap-1.5
