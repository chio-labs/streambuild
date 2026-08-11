<script lang="ts">
	import PlusIcon from '@lucide/svelte/icons/plus';
	import type { MessagePredicate, PredicateField } from '$lib/message-browser/types';

	let {
		knownPartitions,
		onAdd
	}: { knownPartitions: number[]; onAdd: (predicate: MessagePredicate) => void } = $props();

	const OPS_BY_FIELD: Record<PredicateField, string[]> = {
		partition: ['in'],
		key: ['eq', 'contains', 'prefix'],
		value: ['contains'],
		json: ['eq', 'ne', 'contains', 'exists', 'gt', 'lt'],
		header: ['eq', 'contains']
	};
	const OP_HINT: Record<string, string> = {
		eq: 'equals',
		ne: 'not equals',
		contains: 'contains',
		prefix: 'starts with',
		exists: 'exists',
		gt: 'greater than',
		lt: 'less than',
		in: 'in'
	};

	let open = $state<boolean>(false);
	let field = $state<PredicateField>('json');
	let op = $state<string>('eq');
	let text = $state<string>('');
	let path = $state<string>('');
	let selectedPartitions = $state<number[]>([]);

	const ops = $derived(OPS_BY_FIELD[field]);
	const needsValue = $derived(op !== 'exists' && field !== 'partition');
	const numeric = $derived(field === 'json' && (op === 'gt' || op === 'lt'));
	const ready = $derived.by((): boolean => {
		if (field === 'partition') return selectedPartitions.length > 0;
		if (field === 'json' && path.trim() === '') return false;
		if (!needsValue) return true;
		if (numeric) return text.trim() !== '' && Number.isFinite(Number(text));
		return text.trim() !== '';
	});

	function pickField(next: PredicateField): void {
		field = next;
		op = OPS_BY_FIELD[next][0];
	}

	function togglePartition(partition: number): void {
		selectedPartitions = selectedPartitions.includes(partition)
			? selectedPartitions.filter((candidate) => candidate !== partition)
			: [...selectedPartitions, partition].sort((a, b) => a - b);
	}

	function parsedPath(): (string | number)[] {
		return path
			.split('.')
			.map((segment) => segment.trim())
			.filter((segment) => segment !== '')
			.map((segment) => (/^\d+$/.test(segment) ? Number(segment) : segment));
	}

	function add(): void {
		const predicate: MessagePredicate =
			field === 'partition'
				? { field, op: 'in', values: [...selectedPartitions] }
				: field === 'json'
					? op === 'exists'
						? { field, op, path: parsedPath() }
						: { field, op, path: parsedPath(), value: numeric ? Number(text) : text }
					: { field, op, value: text };
		onAdd(predicate);
		open = false;
		text = '';
		path = '';
		selectedPartitions = [];
	}
</script>

<div class="relative">
	<button class="text-muted-foreground hover:text-foreground flex items-center gap-1 rounded-[4px] border border-dashed border-border px-2 py-[3px] font-mono text-[10.5px]" onclick={() => (open = !open)}><PlusIcon size={11} /> filter</button>
	{#if open}
		<div class="bg-background absolute left-0 top-[26px] z-20 w-[300px] rounded-[4px] border border-border p-2.5 shadow-lg">
			<div class="flex flex-wrap gap-1 pb-2">
				{#each Object.keys(OPS_BY_FIELD) as candidate (candidate)}
					<button class="rounded-[4px] border px-2 py-[2px] font-mono text-[10.5px] {field === candidate ? 'border-[var(--primary)] text-foreground' : 'text-muted-foreground border-border hover:text-foreground'}" onclick={() => pickField(candidate as PredicateField)}>{candidate}</button>
				{/each}
			</div>

			{#if field === 'partition'}
				<div class="flex max-h-[120px] flex-wrap gap-1 overflow-auto pb-2">
					{#each knownPartitions as partition (partition)}
						<button class="rounded-[4px] border px-1.5 py-[1px] font-mono text-[10.5px] {selectedPartitions.includes(partition) ? 'border-[var(--primary)] text-foreground' : 'text-muted-foreground border-border'}" onclick={() => togglePartition(partition)}>{partition}</button>
					{/each}
				</div>
			{:else}
				<div class="flex gap-1 pb-2">
					{#each ops as candidate (candidate)}
						<button class="rounded-[4px] border px-1.5 py-[1px] font-mono text-[10px] {op === candidate ? 'border-[var(--primary)] text-foreground' : 'text-muted-foreground border-border hover:text-foreground'}" onclick={() => (op = candidate)} title={OP_HINT[candidate]}>{OP_HINT[candidate]}</button>
					{/each}
				</div>
				{#if field === 'json'}
					<input bind:value={path} placeholder="json path, e.g. data.placer" class="bg-[var(--sb-inset)] mb-1.5 w-full rounded-[4px] border border-border px-2 py-1 font-mono text-[11px] outline-none focus:border-[var(--primary)]" />
				{/if}
				{#if needsValue}
					<input bind:value={text} placeholder={numeric ? 'number' : 'value'} class="bg-[var(--sb-inset)] mb-1.5 w-full rounded-[4px] border border-border px-2 py-1 font-mono text-[11px] outline-none focus:border-[var(--primary)]" onkeydown={(event) => { if (event.key === 'Enter' && ready) add(); }} />
				{/if}
			{/if}

			<div class="flex justify-end gap-1.5">
				<button class="text-muted-foreground hover:text-foreground rounded-[4px] border border-border px-2 py-[3px] font-mono text-[10.5px]" onclick={() => (open = false)}>cancel</button>
				<button class="rounded-[4px] border border-[var(--primary)] px-2 py-[3px] font-mono text-[10.5px] disabled:opacity-40" disabled={!ready} onclick={add}>add</button>
			</div>
		</div>
	{/if}
</div>
