import type { z } from 'zod';
import type { ZodType } from 'zod';
import { usersErrorPayloadSchema } from '../schemas';

export async function readUsersResponse<T>(
	response: Response,
	schema: ZodType<T>,
	operation: string
): Promise<T> {
	if (!response.ok) {
		const payload: unknown = await response.json().catch(() => ({}));
		const errorPayload: z.infer<typeof usersErrorPayloadSchema> | undefined =
			usersErrorPayloadSchema.safeParse(payload).data;
		throw new Error(errorPayload?.detail ?? `${operation} failed with HTTP ${response.status}`);
	}
	return schema.parse(await response.json());
}
