// Single source of truth for every external/brand value on the site.
// Swap SITE_NAME here to rebrand in one edit.

export const SITE_NAME = "Tessera";

// Repository + release/community links
// TODO: point these at the real GitHub org/repo once public.
export const GITHUB_URL = "https://github.com/GridWork-dev/tessera";
export const RELEASES_URL = "https://github.com/GridWork-dev/tessera/releases/latest";
export const DISCUSSIONS_URL = "https://github.com/GridWork-dev/tessera/discussions";

// Commerce — placeholder until the AUP question is cleared.
// TODO: real Polar checkout URL.
export const POLAR_CHECKOUT_URL = "#";
export const PRICE_PRO = "$29";
export const PRICE_FREE = "$0";

// Contact — obfuscated at render time.
const DOMAIN = "gettessera.xyz";
export const EMAIL_CONTACT = `admin@${DOMAIN}`;
export const EMAIL_SALES = `admin@${DOMAIN}`;
export const EMAIL_SECURITY = `admin@${DOMAIN}`;
export const EMAIL_ABUSE = `admin@${DOMAIN}`;

// Security policy (GitHub Private Vulnerability Reporting)
export const SECURITY_URL = `${GITHUB_URL}/security/advisories/new`;

// Per-OS download asset hints (filenames resolved from the latest release).
export const DOWNLOADS = [
  { os: "macOS", ext: ".dmg", note: "Apple silicon + Intel · SHA-256 checksummed", icon: "apple" },
  { os: "Windows", ext: ".exe", note: "Windows 10/11 64-bit · SHA-256 checksummed", icon: "monitor" },
  { os: "Linux", ext: ".AppImage", note: "x86_64 · portable, no install", icon: "terminal" },
] as const;

// Nav order (label -> href)
export const NAV = [
  { label: "Features", href: "/features" },
  { label: "Pricing", href: "/pricing" },
  { label: "Docs", href: "/docs" },
  { label: "Changelog", href: "/changelog" },
] as const;
