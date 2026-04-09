export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponseData {
  access_token: string;
  token_type: string;
}

export interface SignupRequest {
  email: string;
  password: string;
  name: string;
}

export interface SignupResponseData {
  user_id: string;
}

export interface MeResponseData {
  id: string;
  email: string;
  name: string;
}
