import type { AdminUser } from '../types';

export function sourceLabel(user: AdminUser): string {
	if (user.authenticationSources.length === 0) return 'none';
	return user.authenticationSources.join(' + ').replaceAll('_', ' ');
}
