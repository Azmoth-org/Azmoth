"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { ArrowLeft, ArrowUpRight, Building2, Save } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/fetchApi";
import { Button } from "@/components/ui/button";

type CustomerProject = {
  id: string;
  name: string | null;
  status: string;
  phase: string;
  updatedAt: string | Date;
  stages: { id: string; status: string }[];
};

type CustomerDetailData = {
  id: string;
  displayName: string;
  title: string | null;
  givenName: string | null;
  familyName: string | null;
  companyName: string | null;
  primaryEmail: string | null;
  alternateEmail: string | null;
  primaryPhone: string | null;
  mobile: string | null;
  webAddress: string | null;
  taxIdentifier: string | null;
  billingAddress: unknown;
  shippingAddress: unknown;
  notes: string | null;
  createdAt: string | Date;
  user: {
    id: string;
    name: string | null;
    email: string;
    slug: string | null;
    projects: CustomerProject[];
  } | null;
};

type Address = { line1?: string; line2?: string; city?: string; state?: string; postalCode?: string; country?: string };

function parseAddress(value: unknown): Address {
  if (typeof value !== "object" || value === null) return {};
  const obj = value as Record<string, unknown>;
  const pick = (k: string) => (typeof obj[k] === "string" ? (obj[k] as string) : "");
  return { line1: pick("line1"), line2: pick("line2"), city: pick("city"), state: pick("state"), postalCode: pick("postalCode"), country: pick("country") };
}

const inputCls =
  "h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-[13px] text-foreground outline-none transition-colors placeholder:text-[var(--muted)]/50 focus:border-[var(--accent)]";

function Field({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <input className={inputCls} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
    </label>
  );
}

export function CustomerDetail({ customer: initial }: { customer: CustomerDetailData }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [saving, setSaving] = useState(false);

  const [displayName, setDisplayName] = useState(initial.displayName);
  const [companyName, setCompanyName] = useState(initial.companyName ?? "");
  const [title, setTitle] = useState(initial.title ?? "");
  const [givenName, setGivenName] = useState(initial.givenName ?? "");
  const [familyName, setFamilyName] = useState(initial.familyName ?? "");
  const [primaryEmail, setPrimaryEmail] = useState(initial.primaryEmail ?? "");
  const [alternateEmail, setAlternateEmail] = useState(initial.alternateEmail ?? "");
  const [primaryPhone, setPrimaryPhone] = useState(initial.primaryPhone ?? "");
  const [mobile, setMobile] = useState(initial.mobile ?? "");
  const [webAddress, setWebAddress] = useState(initial.webAddress ?? "");
  const [taxIdentifier, setTaxIdentifier] = useState(initial.taxIdentifier ?? "");
  const [notes, setNotes] = useState(initial.notes ?? "");

  const [billing, setBilling] = useState<Address>(parseAddress(initial.billingAddress));

  const setBillingField = (k: keyof Address) => (v: string) => setBilling((b) => ({ ...b, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      await api(`/api/customers/${initial.id}`, "PATCH", {
        displayName,
        companyName,
        title,
        givenName,
        familyName,
        primaryEmail,
        alternateEmail,
        primaryPhone,
        mobile,
        webAddress,
        taxIdentifier,
        notes,
        billingAddress: billing,
      });
      toast.success("Customer profile saved.");
      startTransition(() => router.refresh());
    } catch {
      toast.error("Couldn't save the profile.");
    } finally {
      setSaving(false);
    }
  };

  const projects = initial.user?.projects ?? [];
  const doneCount = (p: CustomerProject) => p.stages.filter((s) => s.status === "done").length;

  return (
    <div className="bg-[var(--background)]">
      <div className="mx-auto max-w-6xl">
        <Button asChild variant="ghost" className="mb-6 px-0 text-sm text-muted-foreground">
          <Link href="/admin/customers">
            <ArrowLeft className="size-4" />
            Customers
          </Link>
        </Button>

        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--accent)]/10 text-lg font-semibold text-[var(--accent)]">
              {(companyName || displayName || "?").charAt(0).toUpperCase()}
            </div>
            <div>
              <h1 className="text-2xl md:text-3xl font-bold tracking-[-0.03em] text-foreground">
                {companyName || displayName}
              </h1>
              <p className="mt-0.5 flex items-center gap-1.5 text-sm text-muted-foreground">
                <Building2 className="size-3.5" />
                {displayName}
                {taxIdentifier && <span className="rounded-full bg-white/5 px-2 py-0.5 text-[11px]">{taxIdentifier}</span>}
              </p>
            </div>
          </div>
          {initial.user?.slug && (
            <Link
              href={`/client/${initial.user.slug}`}
              className="flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-[var(--accent)]"
            >
              <ArrowUpRight className="size-4" />
              View client portal
            </Link>
          )}
        </div>

        <div className="grid gap-6 lg:grid-cols-5">
          {/* Billing profile */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 lg:col-span-3">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Billing profile
            </h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Display name" value={displayName} onChange={setDisplayName} />
              <Field label="Company" value={companyName} onChange={setCompanyName} placeholder="e.g. IPS Tunisie" />
              <Field label="Title" value={title} onChange={setTitle} placeholder="Mr / Mrs / Ms / Dr" />
              <Field label="Tax identifier" value={taxIdentifier} onChange={setTaxIdentifier} placeholder="MF 0000000X for Tunisian businesses" />
              <Field label="First name" value={givenName} onChange={setGivenName} />
              <Field label="Last name" value={familyName} onChange={setFamilyName} />
              <Field label="Primary email" value={primaryEmail} onChange={setPrimaryEmail} />
              <Field label="Alternate email" value={alternateEmail} onChange={setAlternateEmail} />
              <Field label="Primary phone" value={primaryPhone} onChange={setPrimaryPhone} placeholder="+216 …" />
              <Field label="Mobile" value={mobile} onChange={setMobile} />
              <div className="sm:col-span-2">
                <Field label="Website" value={webAddress} onChange={setWebAddress} placeholder="https://…" />
              </div>
            </div>

            <h3 className="mb-3 mt-6 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Billing address
            </h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Address line 1" value={billing.line1 ?? ""} onChange={setBillingField("line1")} />
              <Field label="Address line 2" value={billing.line2 ?? ""} onChange={setBillingField("line2")} />
              <Field label="City" value={billing.city ?? ""} onChange={setBillingField("city")} />
              <Field label="State / province" value={billing.state ?? ""} onChange={setBillingField("state")} />
              <Field label="Postal code" value={billing.postalCode ?? ""} onChange={setBillingField("postalCode")} />
              <Field label="Country" value={billing.country ?? ""} onChange={setBillingField("country")} />
            </div>

            <label className="mt-6 block">
              <span className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Notes</span>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={3}
                placeholder="Internal notes — context, agreements, preferences…"
                className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-[13px] text-foreground outline-none transition-colors placeholder:text-[var(--muted)]/50 focus:border-[var(--accent)]"
              />
            </label>

            <div className="mt-6 flex justify-end">
              <Button onClick={save} disabled={saving} className="gap-2">
                <Save className="size-4" />
                {saving ? "Saving…" : "Save profile"}
              </Button>
            </div>
          </div>

          {/* Projects */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 lg:col-span-2">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Projects ({projects.length})
            </h2>
            {projects.length === 0 ? (
              <p className="text-sm text-muted-foreground">No projects linked to this customer yet.</p>
            ) : (
              <ul className="space-y-2">
                {projects.map((p) => {
                  const done = doneCount(p);
                  const pct = p.stages.length ? Math.round((done / p.stages.length) * 100) : 0;
                  return (
                    <li key={p.id}>
                      <Link
                        href={`/admin/projects/${p.id}`}
                        className="block rounded-xl border border-[var(--border)] bg-[var(--background)] p-3 transition-colors hover:border-[var(--accent)]/40"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-[13px] font-medium text-foreground">{p.name ?? "Untitled"}</p>
                          <span className="text-[11px] capitalize text-muted-foreground">
                            {p.status.replace("_", " ")}
                          </span>
                        </div>
                        <div className="mt-2 flex items-center gap-2">
                          <div className="h-1 flex-1 overflow-hidden rounded-full bg-[var(--border)]">
                            <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-[10px] text-muted-foreground">{pct}%</span>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
