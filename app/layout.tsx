import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import { headers } from "next/headers";
import { CLUB_DESCRIPTION, CLUB_IDENTITY, CLUB_PAGE_TITLE } from "./data/mock-course";
import "./globals.css";

const geist = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("host") ?? "localhost:3000";
  const protocol = host.startsWith("localhost") || host.startsWith("127.0.0.1") ? "http" : "https";
  const metadataBase = new URL(`${protocol}://${host}`);

  const socialTitle = CLUB_IDENTITY.fullName;
  const socialDescription = `Your game at ${CLUB_IDENTITY.fullName}, one round at a time.`;

  return {
    metadataBase,
    title: CLUB_PAGE_TITLE,
    description: CLUB_DESCRIPTION,
    applicationName: CLUB_IDENTITY.shortName,
    manifest: "/manifest.webmanifest",
    formatDetection: { telephone: false },
    appleWebApp: {
      capable: true,
      statusBarStyle: "black-translucent",
      title: CLUB_IDENTITY.shortName,
    },
    icons: {
      icon: "/favicon.svg",
      shortcut: "/favicon.svg",
      apple: "/favicon.svg",
    },
    openGraph: {
      title: socialTitle,
      description: socialDescription,
      type: "website",
      images: [{ url: "/og.png", width: 1536, height: 1024, alt: `Illustrated course atlas for ${CLUB_IDENTITY.fullName} in ${CLUB_IDENTITY.location}` }],
    },
    twitter: {
      card: "summary_large_image",
      title: socialTitle,
      description: socialDescription,
      images: ["/og.png"],
    },
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#123d2c" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0f12" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={geist.variable}>{children}</body>
    </html>
  );
}
