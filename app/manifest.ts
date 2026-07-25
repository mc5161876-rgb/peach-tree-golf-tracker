import type { MetadataRoute } from "next";
import { CLUB_DESCRIPTION, CLUB_IDENTITY, CLUB_PAGE_TITLE } from "./data/mock-course";

/**
 * Served at /manifest.webmanifest.
 *
 * Generated rather than kept as a static file in public/ so the installed
 * home-screen identity always follows CLUB_IDENTITY. The previous static file
 * had drifted into a mis-encoded em-dash; generating the JSON removes that
 * whole class of problem.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: CLUB_PAGE_TITLE,
    short_name: CLUB_IDENTITY.shortName,
    description: CLUB_DESCRIPTION,
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait-primary",
    background_color: "#f3eddf",
    theme_color: "#123d2c",
    // Raster rather than SVG: the crest is generated artwork, and both the
    // hand-traced and Codex-authored vector versions distorted the peach's
    // proportions. Next's Manifest type allows one purpose per entry, so the
    // maskable declaration is a second entry — equivalent to the
    // space-separated "any maskable" form per the spec.
    icons: [
      { src: "/icons/crest-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/crest-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/crest-512-fullbleed.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
