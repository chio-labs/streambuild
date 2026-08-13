import type { z } from 'zod';
import type { ZodType } from 'zod';
import { authErrorPayloadSchema } from '../schemas';

export async function readAuthResponse<T>(
	response: Response,
	schema: ZodType<T>,
	operation: string
): Promise<T> {
	if (!response.ok) {
		const payload: unknown = await response.json().catch(() => ({}));
		const errorPayload: z.infer<typeof authErrorPayloadSchema> | undefined =
			authErrorPayloadSchema.safeParse(payload).data;
		throw new Error(errorPayload?.detail ?? `${operation} failed with HTTP ${response.status}`);
	}
	return schema.parse(await response.json());
}
