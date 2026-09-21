// Persian display names for the seeded system roles. Role *names* are data
// (English by seed); this mapping is display-only — custom roles (and any
// renamed system role) fall back to the stored name.
const ROLE_FA: Record<string, string> = {
  admin: 'مدیر',
  doctor: 'پزشک',
  receptionist: 'منشی',
}

export function roleFa(name: string): string {
  return ROLE_FA[name] ?? name
}
