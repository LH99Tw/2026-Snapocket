import type { DocumentDetail } from '../model/types'

export const MOCK_DOCUMENTS: Record<string, DocumentDetail> = {
  'mock-1': {
    id: 'mock-1',
    title: 'CS204 Operating Systems — Week 9 Lecture',
    category: 'Class Materials',
    summary:
      'Covers process scheduling algorithms including Round Robin, SJF, and Priority Scheduling. Key topics: context switching overhead, starvation prevention via aging, and multilevel feedback queues. Includes worked examples from the midterm review session.',
    tags: ['CS-204', 'OS', 'Scheduling', 'Midterm'],
    file_url: '',
    file_type: 'image',
    status: 'analyzed',
    capture_date: '2026-04-01T00:00:00.000Z',
    deadline: null,
    created_at: '2026-04-01T14:23:00.000Z',
  },
  'mock-2': {
    id: 'mock-2',
    title: 'Algorithm Analysis — Assignment 3',
    category: 'Assignments',
    summary:
      'Assignment 3 focuses on dynamic programming and graph algorithms. Problems include optimal binary search trees, longest common subsequence, Bellman-Ford shortest path, and a bonus problem on network flow. Submission deadline is April 14.',
    tags: ['CS-301', 'Algorithms', 'DP', 'Graphs'],
    file_url: '',
    file_type: 'image',
    status: 'analyzed',
    capture_date: '2026-04-05T00:00:00.000Z',
    deadline: '2026-04-14T23:59:00.000Z',
    created_at: '2026-04-05T09:10:00.000Z',
  },
}
