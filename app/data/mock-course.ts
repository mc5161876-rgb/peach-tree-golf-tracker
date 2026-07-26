/**
 * Single source of truth for the club's identity.
 *
 * The app is branded to the course, not to a product name. If the club renames
 * (a move to "Yuba Golf Club" has been discussed), edit this block and nothing
 * else: the header, page title, social metadata, and PWA manifest all read from
 * here.
 */
export const CLUB_IDENTITY = {
  /** Short name used as the header wordmark. */
  wordmark: "Peach Tree",
  /** Full legal-ish name used in titles, metadata, and round history. */
  fullName: "Peach Tree Golf & Country Club",
  /** Second line under the wordmark in the app header. */
  headerSubtitle: "Golf & Country Club · Marysville",
  /** Town and state, used in descriptive copy. */
  location: "Marysville, California",
  /** Town on its own, for tighter labels like "Home course · Marysville". */
  locality: "Marysville",
  /** Crest letters shown in the header mark and course banner. */
  crest: "PT",
  /** What the app does. Used in metadata, never as a brand name in the UI. */
  tagline: "Personal golf scoring",
  /** Home-screen name once installed. Keep short — iOS truncates past ~12 chars. */
  shortName: "Peach Tree",
} as const;

export const CLUB_PAGE_TITLE = `${CLUB_IDENTITY.fullName} — ${CLUB_IDENTITY.tagline}`;
export const CLUB_DESCRIPTION = `Personal golf scoring and illustrated hole guides for ${CLUB_IDENTITY.fullName} in ${CLUB_IDENTITY.location}.`;

export type Tee = "black" | "blue" | "white" | "combo" | "green";

export const TEE_OPTIONS: { value: Tee; label: string; shortLabel: string; total: number }[] = [
  { value: "black", label: "Black", shortLabel: "Black", total: 6898 },
  { value: "blue", label: "Blue", shortLabel: "Blue", total: 6784 },
  { value: "white", label: "White", shortLabel: "White", total: 6478 },
  { value: "combo", label: "White / Green", shortLabel: "W / G", total: 6146 },
  { value: "green", label: "Green", shortLabel: "Green", total: 5989 },
];

export const teeLabel = (tee: Tee) => TEE_OPTIONS.find((option) => option.value === tee)?.label ?? tee;

export type Hole = {
  number: number;
  par: 3 | 4 | 5;
  strokeIndex: number;
  yardages: Record<Tee, number>;
  visual: {
    src: string;
    alt: string;
    illustratedSrc?: string;
    illustratedAlt?: string;
  };
  localNote?: string;
};

const hole = (
  number: number,
  par: 3 | 4 | 5,
  strokeIndex: number,
  yardages: Record<Tee, number>,
  extras: {
    illustratedSrc?: string;
    illustratedAlt?: string;
    localNote?: string;
  } = {},
): Hole => ({
  number,
  par,
  strokeIndex,
  yardages,
  visual: {
    src: `/course/peach-tree/hole-${String(number).padStart(2, "0")}.webp`,
    alt: `Aerial course guide for Peach Tree hole ${number}, showing the real fairway corridor, trees, bunkers, and surrounding terrain`,
    illustratedSrc: extras.illustratedSrc ?? `/course/peach-tree/hole-${String(number).padStart(2, "0")}-illustrated.png`,
    illustratedAlt: extras.illustratedAlt ?? `AI-illustrated aerial course guide for Peach Tree hole ${number}, derived from the real aerial layout with modeled trees, terrain, fairway, green, and hazards`,
  },
  localNote: extras.localNote,
});

export const HOME_COURSE = {
  id: "peach-tree",
  name: CLUB_IDENTITY.fullName,
  shortName: CLUB_IDENTITY.wordmark,
  location: CLUB_IDENTITY.location,
  address: "2043 Simpson Dantoni Road",
  monogram: CLUB_IDENTITY.crest,
  par: 72,
  /**
   * Banner image on the "Let's play" screen. An AI-generated impression of the
   * course at golden hour, not a photograph and not survey imagery — see
   * heroCredit. The real 2022 NAIP aerial is still produced by the atlas
   * generator as course-aerial.webp and remains the source for the hole cards.
   */
  hero: "/course/peach-tree/clubhouse-hero.webp",
  heroCredit: "Illustrated impression of the course · not a photograph",
  guideLabel: "Illustrated course guide · not GPS",
  guideCredit: "2022 USDA NAIP imagery via USGS · hole routes © OpenStreetMap contributors",
  scorecardNote: "Course-reference yardages · verify against the current club scorecard",
  holes: [
    hole(1, 4, 11, { black: 407, blue: 401, white: 386, combo: 370, green: 370 }, {
      illustratedSrc: "/course/peach-tree/hole-01-illustrated.png",
      illustratedAlt: "AI-illustrated aerial course guide for Peach Tree hole 1, preserving the narrow tree-lined fairway, green, and greenside bunkers from the real aerial reference",
    }),
    hole(2, 5, 7, { black: 530, blue: 524, white: 507, combo: 507, green: 491 }),
    hole(3, 3, 17, { black: 173, blue: 164, white: 155, combo: 140, green: 140 }),
    hole(4, 4, 1, { black: 440, blue: 433, white: 412, combo: 338, green: 338 }, {
      localNote: "Current local knowledge: the dogleg left begins earlier than it appears in the July 2022 aerial. Exact revised geometry is still to be confirmed.",
    }),
    hole(5, 4, 5, { black: 458, blue: 452, white: 434, combo: 417, green: 417 }),
    hole(6, 5, 3, { black: 503, blue: 497, white: 479, combo: 479, green: 462 }),
    hole(7, 3, 9, { black: 225, blue: 219, white: 200, combo: 144, green: 144 }),
    hole(8, 4, 13, { black: 386, blue: 379, white: 362, combo: 362, green: 344 }),
    hole(9, 4, 15, { black: 358, blue: 353, white: 338, combo: 338, green: 324 }),
    hole(10, 4, 8, { black: 371, blue: 366, white: 351, combo: 351, green: 337 }),
    hole(11, 5, 4, { black: 505, blue: 497, white: 475, combo: 475, green: 453 }),
    hole(12, 4, 2, { black: 426, blue: 420, white: 402, combo: 322, green: 322 }),
    hole(13, 4, 14, { black: 390, blue: 383, white: 363, combo: 363, green: 343 }),
    hole(14, 3, 18, { black: 193, blue: 188, white: 176, combo: 176, green: 158 }),
    hole(15, 4, 10, { black: 383, blue: 378, white: 362, combo: 347, green: 347 }),
    hole(16, 4, 12, { black: 412, blue: 406, white: 387, combo: 343, green: 343 }),
    hole(17, 3, 16, { black: 189, blue: 184, white: 169, combo: 154, green: 154 }),
    hole(18, 5, 6, { black: 549, blue: 540, white: 520, combo: 520, green: 502 }),
  ] satisfies Hole[],
};

export const POSITIVE_TAGS = [
  "Great drive",
  "Fairway hit",
  "Great approach",
  "Green in regulation",
  "Up-and-down",
  "Sand save",
  "One-putt",
  "Long putt made",
  "Smart course management",
  "Recovery shot",
] as const;

export const NEGATIVE_TAGS = [
  "Bad drive",
  "Drive out of position",
  "Penalty",
  "Bad approach",
  "Missed green",
  "Bunker trouble",
  "Poor chip/pitch",
  "Three-putt",
  "Short putt missed",
  "Course-management mistake",
] as const;
