export type LoginFormState = {
	username: string;
	password: string;
	submitting: boolean;
	error: string | null;
};

export type LoginController = {
	readonly form: LoginFormState;
	submit(): Promise<void>;
};
