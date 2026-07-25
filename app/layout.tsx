import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import { headers } from "next/headers";
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

  return {
    metadataBase,
    title: "Roundwell at Peach Tree — Personal Golf Scoring",
    description: "Premium mobile golf scoring and illustrated hole guides for Peach Tree Golf & Country Club in Marysville, California.",
    applicationName: "Roundwell",
    manifest: "/manifest.webmanifest",
    formatDetection: { telephone: false },
    appleWebApp: {
      capable: true,
      statusBarStyle: "black-translucent",
      title: "Roundwell",
    },
    icons: {
      icon: "/favicon.svg",
      shortcut: "/favicon.svg",
      apple: "/favicon.svg",
    },
    openGraph: {
      title: "Roundwell at Peach Tree",
      description: "Your game at Peach Tree Golf & Country Club, one round at a time.",
      type: "website",
      images: [{ url: "/og.png", width: 1536, height: 1024, alt: "Roundwell course atlas for Peach Tree Golf & Country Club in Marysville, California" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "Roundwell at Peach Tree",
      description: "Your game at Peach Tree Golf & Country Club, one round at a time.",
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
