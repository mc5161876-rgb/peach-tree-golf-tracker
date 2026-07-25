import type { Tee } from "./mock-course";

export type MockRound = {
  id: string;
  date: string;
  tee: Tee;
  holes: number;
  scoredHoles?: number;
  startingHole?: number;
  score: number;
  toPar: number;
  holeScores: number[];
  tags: string[];
};

export const MOCK_ROUNDS: MockRound[] = [
  {
    id: "mock-1",
    date: "Jul 8, 2026",
    tee: "blue",
    holes: 18,
    score: 82,
    toPar: 10,
    holeScores: [4, 5, 3, 5, 4, 4, 5, 4, 5, 4, 3, 6, 4, 5, 3, 6, 4, 4],
    tags: ["Great drive", "Fairway hit", "Three-putt", "Bad approach"],
  },
  {
    id: "mock-2",
    date: "Jul 3, 2026",
    tee: "white",
    holes: 18,
    score: 79,
    toPar: 7,
    holeScores: [4, 5, 3, 4, 4, 3, 6, 4, 4, 4, 3, 5, 5, 4, 4, 6, 4, 5],
    tags: ["Green in regulation", "One-putt", "Great approach", "Penalty"],
  },
  {
    id: "mock-3",
    date: "Jun 27, 2026",
    tee: "blue",
    holes: 18,
    score: 86,
    toPar: 14,
    holeScores: [5, 6, 3, 5, 5, 4, 6, 4, 5, 4, 4, 6, 4, 5, 3, 6, 5, 4],
    tags: ["Bad drive", "Missed green", "Poor chip/pitch", "Recovery shot"],
  },
  {
    id: "mock-4",
    date: "Jun 20, 2026",
    tee: "white",
    holes: 9,
    score: 39,
    toPar: 3,
    holeScores: [4, 5, 3, 4, 4, 3, 6, 4, 6],
    tags: ["Fairway hit", "Up-and-down", "Short putt missed"],
  },
];
