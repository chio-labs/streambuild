<script lang="ts">
	import { formatDuration } from '$lib/formatting/main/format-duration';

	type Props = {
		severity: string;
		scheduled: boolean;
		cadenceSeconds: number | null;
		warmupSeconds: number;
	};

	const { severity, scheduled, cadenceSeconds, warmupSeconds }: Props = $props();
</script>

<div class="flex gap-4 font-mono text-[10.5px] text-[var(--sb-text-faint)]">
	<span>severity {severity}</span>
	<span>{scheduled ? `every ${formatDuration(cadenceSeconds ?? 0)}` : 'manual/build only'}</span>
	<span>warmup {formatDuration(warmupSeconds)}</span>
</div>
