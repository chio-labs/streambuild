import { getAuth } from '$lib/auth/main/get-auth';
import { initializeAuth } from '$lib/auth/main/initialize-auth';
import { initializeApp } from '$lib/api/main/project/initialize-app';

export async function initializeBootstrap(): Promise<void> {
	await initializeAuth();
	if (getAuth().phase === 'authenticated') await initializeApp();
}
