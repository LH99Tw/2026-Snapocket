import { BASE_URL, ApiError, apiClient, getAccessToken } from "@/shared/api";
import type {
  ApiNode,
  ApiNodeCategory,
  GraphSummaryData,
  SearchNodeResult,
} from "./graph.api.type";

interface GraphQLResponse<T> {
  data: T;
  errors?: { message: string; extensions?: { code: string } }[];
}

async function graphqlRequest<T>(
  query: string,
  variables?: Record<string, unknown>
): Promise<T> {
  const token = getAccessToken();
  const res = await fetch(`${BASE_URL}/graphql`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ query, variables }),
  });

  const body = (await res.json()) as GraphQLResponse<T>;
  const firstError = body.errors?.[0];

  if (!res.ok) {
    throw new ApiError(res.status, firstError?.message ?? res.statusText, firstError?.extensions?.code);
  }

  if (firstError) {
    throw new ApiError(200, firstError.message, firstError.extensions?.code);
  }

  return body.data;
}

export async function getNodes(category?: ApiNodeCategory): Promise<ApiNode[]> {
  const variables = category !== undefined ? { category } : {};
  const data = await graphqlRequest<{ nodes: ApiNode[] }>(
    "query GetNodes($category: String) { nodes(category: $category) { id title category tags created_at connection_count } }",
    variables
  );
  return data.nodes;
}

export async function searchNodes(q: string): Promise<SearchNodeResult[]> {
  const data = await graphqlRequest<{ searchNodes: SearchNodeResult[] }>(
    "query SearchNodes($q: String!) { searchNodes(query: $q) { id title category highlight } }",
    { q }
  );
  return data.searchNodes;
}

export async function getGraphSummary(): Promise<GraphSummaryData> {
  const res = await apiClient<GraphSummaryData>("/graph/summary", {
    requireAuth: true,
  });
  return res.data;
}
