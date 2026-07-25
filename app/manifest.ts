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
    // The static manifest declared a single icon with purpose "any maskable".
    // Next's Manifest type only accepts one purpose per entry, so the same icon
    // is listed twice — equivalent to the space-separated form per the spec.
    icons: [
      { src: "/favicon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/favicon.svg", sizes: "any", type: "image/svg+xml", purpose: "maskable" },
    ],
  };
}
