import { apiClient, saveAccessToken, clearAccessToken } from "@/shared/api";
import type {
  LoginRequest,
  LoginResponseData,
  SignupRequest,
  SignupResponseData,
  MeResponseData,
} from "./auth.api.type";

export async function login(body: LoginRequest): Promise<LoginResponseData> {
  const res = await apiClient<LoginResponseData>("/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
  saveAccessToken(res.data.access_token);
  return res.data;
}

export async function signup(body: SignupRequest): Promise<SignupResponseData> {
  const res = await apiClient<SignupResponseData>("/auth/signup", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return res.data;
}

export async function getMe(): Promise<MeResponseData> {
  const res = await apiClient<MeResponseData>("/auth/me", {
    requireAuth: true,
  });
  return res.data;
}

export async function logout(): Promise<void> {
  await apiClient<null>("/auth/logout", {
    method: "POST",
    requireAuth: true,
  });
  clearAccessToken();
}
