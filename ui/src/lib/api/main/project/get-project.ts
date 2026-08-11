import { getAppInstance } from '$lib/api/_helpers/app-instance.svelte';
import type { Project } from '$lib/domain/types';

export function getProject(): Project {
	const project: Project | null = getAppInstance().app.project;
	if (project === null) throw new Error('getProject() called before the app finished loading');
	return project;
}
