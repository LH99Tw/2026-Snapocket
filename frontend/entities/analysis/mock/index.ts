import type { AnalysisResult } from '../model/types'

export const MOCK_RESULTS: Record<string, AnalysisResult> = {
  'mock-1': {
    title: 'CS204 Operating Systems — Week 9 Lecture',
    category: 'Class Materials',
    capture_date: '2026-04-01T00:00:00.000Z',
    summary:
      'Covers process scheduling algorithms including Round Robin, SJF, and Priority Scheduling. Key topics: context switching overhead, starvation prevention via aging, and multilevel feedback queues. Includes worked examples from the midterm review session.',
    tags: ['CS-204', 'OS', 'Scheduling', 'Midterm'],
    raw_text: '',
    key_concepts: ['Round Robin', 'SJF', 'Priority Scheduling', 'Context Switch', 'Aging'],
    deadline: null,
  },
  'mock-2': {
    title: 'Algorithm Analysis — Assignment 3',
    category: 'Assignments',
    capture_date: '2026-04-05T00:00:00.000Z',
    summary:
      'Assignment 3 focuses on dynamic programming and graph algorithms. Problems include optimal binary search trees, longest common subsequence, Bellman-Ford shortest path, and a bonus problem on network flow. Submission deadline is April 14.',
    tags: ['CS-301', 'Algorithms', 'DP', 'Graphs'],
    raw_text: '',
    key_concepts: ['Dynamic Programming', 'Bellman-Ford', 'LCS', 'Network Flow', 'BST'],
    deadline: '2026-04-14T23:59:00.000Z',
  },
}
