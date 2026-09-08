import { AlertTriangle } from "lucide-react";
import { TERMS_OF_SERVICE, PRIVACY_POLICY } from "./legalContent";

/**
 * LegalDocument
 *
 * Public /terms and /privacy pages. Renders from legalContent.js so
 * the Terms of Service and Privacy Policy have exactly one real
 * source of text each, not duplicated inline here.
 *
 * The banner below is NOT decorative - this content has not been
 * reviewed by an attorney (see legalContent.js's own docstring), and
 * this page says so plainly rather than presenting draft legal text
 * as if it were finalized. Do not remove this banner until real
 * counsel has actually reviewed the content and you are ready to
 * treat it as your live, binding policy - at which point also update
 * the bracketed placeholders ([EFFECTIVE DATE], contact emails, your
 * state, etc.) throughout legalContent.js with real values.
 */
function DraftBanner() {
  return (
    <div className="bg-amber-50 border border-amber-300 rounded-lg px-4 py-3 mb-6 flex gap-2.5">
      <AlertTriangle size={18} className="text-amber-600 shrink-0 mt-0.5" />
      <div className="text-xs text-amber-800 leading-relaxed">
        <p className="font-semibold mb-0.5">Draft — pending attorney review</p>
        <p>
          This document has not yet been reviewed by an attorney and is not
          in final, binding form. Bracketed placeholders below have not been
          filled in with real values.
        </p>
      </div>
    </div>
  );
}

function SubprocessorTable({ rows }) {
  return (
    <div className="overflow-x-auto my-3 border border-slate-200 rounded-lg">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-slate-800 text-white">
            <th className="text-left font-semibold px-3 py-2">Subprocessor</th>
            <th className="text-left font-semibold px-3 py-2">Purpose</th>
            <th className="text-left font-semibold px-3 py-2">Data Involved</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name} className="border-t border-slate-100">
              <td className="px-3 py-2 align-top font-medium text-slate-700">{r.name}</td>
              <td className="px-3 py-2 align-top text-slate-600">{r.purpose}</td>
              <td className="px-3 py-2 align-top text-slate-600">{r.data}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentBody({ doc }) {
  return (
    <>
      <h1 className="text-2xl font-serif font-bold text-slate-900 mb-1">{doc.title}</h1>
      <p className="text-xs text-slate-400 italic mb-5">Effective Date: {doc.effectiveDate}</p>
      <DraftBanner />
      {doc.sections.map((section) => (
        <div key={section.heading} className="mb-5">
          <h2 className="text-base font-semibold text-slate-800 mb-1.5">{section.heading}</h2>
          {section.paragraphs.map((para, i) => (
            <p key={i} className="text-sm text-slate-600 leading-relaxed mb-2">{para}</p>
          ))}
          {section.table && <SubprocessorTable rows={section.table} />}
        </div>
      ))}
    </>
  );
}

/** type: "terms" | "privacy" */
export default function LegalDocument({ type }) {
  const doc = type === "privacy" ? PRIVACY_POLICY : TERMS_OF_SERVICE;
  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4">
      <div className="max-w-2xl mx-auto bg-white border border-slate-200 rounded-xl p-6 sm:p-8">
        <a href="/" className="text-xs text-indigo-600 underline">&larr; Back</a>
        <div className="mt-3">
          <DocumentBody doc={doc} />
        </div>
      </div>
    </div>
  );
}
