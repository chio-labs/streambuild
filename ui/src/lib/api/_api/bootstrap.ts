import { z } from 'zod';
import { readApiResponse } from '$lib/api/_api/read-response';
import type { BootstrapPayload } from '$lib/api/types';
import {
	authConfigSchema,
	authPayloadSchema,
	capabilitiesSchema
} from '$lib/auth/schemas';

const recordSchema = z.record(z.string(), z.unknown());
const bootstrapSchema = z.object({
	auth: z.object({
		config: authConfigSchema,
		session: authPayloadSchema,
		capabilities: capabilitiesSchema.nullable()
	}),
	status: recordSchema,
	definitions: recordSchema.nullable(),
	state: recordSchema.nullable()
});

export async function requestBootstrapPayload(): Promise<BootstrapPayload | null> {
	const response: Response = await fetch('/api/bootstrap');
	if (response.status === 401) return null;
	const payload: unknown = await readApiResponse<unknown>(response, 'bootstrap');
	return bootstrapSchema.parse(payload);
}
