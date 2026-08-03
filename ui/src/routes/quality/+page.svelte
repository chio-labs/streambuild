<script lang="ts">
	import PlayIcon from '@lucide/svelte/icons/play';
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right';
	import AppTopbar from '$lib/components/app-topbar.svelte';
	import SqlBlock from '$lib/components/sql-block.svelte';
	import { getProject, runCheck } from '$lib/api';
	import { auditCounts, testCounts } from '$lib/domain/derive';
	import { formatAgo, formatInteger } from '$lib/domain/format';
	import type { Audit, CellValue, Project, SqlTest } from '$lib/domain/types';

	const project: Project = getProject();

	// Audits and tests are RUNNABLE here even though the UI is read-only: in
	// StreamBuild both go through client.query() and never the mutation gateway.
	// Only `build` writes.
	const audits = $derived(auditCounts(project.audits));
	const tests = $derived(testCounts(project.tests));

	type Filter = 'all' | 'failing' | 'passing';
	let filter = $state<Filter>('all');

	// Collapsed by default — the list is far easier to scan, and the row already
	// carries the outcome. Expand is opt-in.
	let expandedAudit = $state<string | null>(null);
	let expandedTest = $state<string | null>(null);

	// A check that has never run is neither passing nor failing — it only shows
	// under "All". Fabricating an outcome for it was worse than useless.
	function auditVisible(audit: Audit): boolean {
		if (filter === 'all') return true;
		if (!audit.result) return false;
		return filter === 'passing' ? audit.result.passed : !audit.result.passed;
	}

	function testVisible(test: SqlTest): boolean {
		if (filter === 'all') return true;
		if (!test.result) return false;
		return filter === 'passing' ? test.result.passed : !test.result.passed;
	}

	function cell(value: CellValue): string {
		if (value === null) return 'NULL';
		if (value === '') return '‹empty›';
		return String(value);
	}

	const visibleAudits = $derived(project.audits.filter(auditVisible));
	const visibleTests = $derived(project.tests.filter(testVisible));

	let runningCheck = $state<string | null>(null);
	let runError = $state<string | null>(null);
	let runningAll = $state<'audits' | 'tests' | null>(null);
	let runAllProgress = $state<number>(0);

	async function executeAudit(name: string): Promise<void> {
		runningCheck = name;
		runError = null;
		try {
			const outcome = await runCheck('audit', name);
			const audit = project.audits.find((item) => item.name === name);
			if (audit) {
				audit.result = {
					passed: outcome.passed,
					failingRowCount: outcome.failingRowCount ?? 0,
					sampleColumns: outcome.sampleColumns ?? [],
					sampleRows: outcome.sampleRows ?? [],
					checkedAt: new Date().toISOString()
				};
			}
		} catch (error) {
			runError = String(error);
		} finally {
			runningCheck = null;
		}
	}

	async function executeTest(name: string): Promise<void> {
		runningCheck = name;
		runError = null;
		try {
			const outcome = await runCheck('test', name);
			const test = project.tests.find((item) => item.name === name);
			if (test) {
				test.result = {
					passed: outcome.passed,
					targets: (outcome.targets ?? []).map((target) => ({
						targetModelName: target.targetModelName,
						passed: target.passed,
						columns: target.columns ?? [],
						missingRows: target.missingRows ?? [],
						unexpectedRows: target.unexpectedRows ?? []
					})),
					checkedAt: new Date().toISOString(),
					errorMessage: outcome.errorMessage ?? null
				};
			}
		} catch (error) {
			runError = String(error);
		} finally {
			runningCheck = null;
		}
	}

	// Sequential on purpose: each check is one warehouse query, and hammering a
	// dev ClickHouse with 19 concurrent scans helps nobody.
	async function executeAllAudits(): Promise<void> {
		runningAll = 'audits';
		runAllProgress = 0;
		for (const audit of project.audits) {
			await executeAudit(audit.name);
			runAllProgress += 1;
		}
		runningAll = null;
	}

	async function executeAllTests(): Promise<void> {
		runningAll = 'tests';
		runAllProgress = 0;
		for (const test of project.tests) {
			await executeTest(test.name);
			runAllProgress += 1;
		}
		runningAll = null;
	}
</script>

<AppTopbar title="Quality">
	<button
		class="text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded-[4px] border border-border px-2.5 py-1.5 font-mono text-[11px] disabled:opacity-60"
		disabled={runningAll !== null || runningCheck !== null}
		onclick={() => void executeAllAudits()}
	>
		<PlayIcon size={11} />
		{runningAll === 'audits'
			? `running ${runAllProgress + 1}/${project.audits.length}…`
			: 'Run audits'}
	</button>
	<button
		class="text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded-[4px] border border-border px-2.5 py-1.5 font-mono text-[11px] disabled:opacity-60"
		disabled={runningAll !== null || runningCheck !== null}
		onclick={() => void executeAllTests()}
	>
		<PlayIcon size={11} />
		{runningAll === 'tests' ? `running ${runAllProgress + 1}/${project.tests.length}…` : 'Run tests'}
	</button>
</AppTopbar>

<div class="min-h-0 flex-1 overflow-y-auto">
	<div class="flex items-center gap-2.5 border-b border-border px-[18px] py-2.5">
		{#each [['all', 'All'], ['failing', 'Failing'], ['passing', 'Passing']] as [key, label] (key)}
			<button
				class="rounded-[4px] border px-2.5 py-1.5 font-mono text-[11px] transition-colors {filter ===
				key
					? 'border-primary text-foreground bg-[var(--sidebar-accent)]'
					: 'text-muted-foreground hover:text-foreground border-border'}"
				onclick={() => (filter = key as Filter)}
			>
				{label}
			</button>
		{/each}
		<span class="text-muted-foreground ml-auto font-mono text-[11px]">
			audits {audits.passing}/{audits.total}
			{#if audits.warning}· <span style:color="var(--sb-warning)">{audits.warning} warn</span>{/if}
			{#if audits.failing}· <span style:color="var(--sb-error)">{audits.failing} fail</span>{/if}
			· tests {tests.passing}/{tests.total}
			{#if tests.failing}· <span style:color="var(--sb-error)">{tests.failing} fail</span>{/if}
		</span>
	</div>

	<div class="flex flex-col gap-6 p-[18px]">
		<!-- ── audits ──────────────────────────────────────────────────────── -->
		<div>
			<div
				class="text-[var(--sb-text-faint)] flex items-baseline gap-2 pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
			>
				Audits
			</div>

			<div class="overflow-hidden rounded-[4px] border border-border">
				{#each visibleAudits as audit (audit.name)}
					{@const failing = audit.result && !audit.result.passed}
					<div class="border-b border-[var(--border-subtle)] last:border-b-0">
						<button
							class="hover:bg-[var(--sb-hover)] flex w-full items-center gap-3 px-3 py-2 text-left"
							onclick={() => (expandedAudit = expandedAudit === audit.name ? null : audit.name)}
						>
							<span
								class="shrink-0 transition-transform"
								style:transform={expandedAudit === audit.name ? 'rotate(90deg)' : 'none'}
								><ChevronRightIcon size={12} class="text-muted-foreground" /></span
							>
							<span
								class="h-1.5 w-1.5 shrink-0 rounded-[2px]"
								style:background={!audit.result
									? 'var(--border)'
									: audit.result.passed
										? 'var(--sb-success)'
										: audit.severity === 'warning'
											? 'var(--sb-warning)'
											: 'var(--sb-error)'}
							></span>
							<span class="code min-w-0 flex-1 truncate text-[12px]">{audit.name}</span>
							<span class="w-[70px] shrink-0 font-mono text-[10.5px]">
								{#if audit.generic}
									<span class="text-[var(--sb-text-faint)]">generic</span>
								{:else}
									<span class="text-[var(--sb-text-faint)]">singular</span>
								{/if}
							</span>
							<span
								class="w-[64px] shrink-0 font-mono text-[10.5px]"
								style:color={audit.severity === 'warning'
									? 'var(--sb-warning)'
									: 'var(--sb-text-faint)'}>{audit.severity}</span
							>
							<span class="w-[170px] shrink-0 truncate font-mono text-[11px]">
								{#each audit.referencedModels as model, index (model)}
									<a href="/catalog/{model}" class="text-primary hover:underline"
										>{model}</a
									>{#if index < audit.referencedModels.length - 1}, {/if}
								{/each}
							</span>
							<span class="w-[92px] shrink-0 text-right font-mono text-[11px]">
								{#if !audit.result}
									<span class="text-[var(--sb-text-faint)]">not run</span>
								{:else if failing}
									<span style:color={audit.severity === 'warning' ? 'var(--sb-warning)' : 'var(--sb-error)'}
										>{formatInteger(audit.result.failingRowCount)} rows</span
									>
								{:else}
									<span style:color="var(--sb-success)">pass</span>
								{/if}
							</span>
							<span class="text-[var(--sb-text-faint)] w-[74px] shrink-0 text-right font-mono text-[10.5px]"
								>{formatAgo(audit.result?.checkedAt ?? null, project.capturedAt)}</span
							>
						</button>

						{#if expandedAudit === audit.name}
							<div class="flex flex-col gap-3 border-t border-[var(--border-subtle)] px-3 py-3">
								<div class="flex items-center gap-2">
									<button
										class="text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px] disabled:opacity-60"
										disabled={runningCheck !== null}
										onclick={() => void executeAudit(audit.name)}
									>
										{runningCheck === audit.name ? 'running…' : 'run audit'}
									</button>
									{#if runError && runningCheck === null}
										<span class="font-mono text-[11px]" style:color="var(--sb-error)">{runError}</span>
									{/if}
								</div>
								{#if audit.description}
									<p class="text-muted-foreground text-[12px] leading-relaxed">
										{audit.description}
									</p>
								{/if}

								<!-- Sample violating rows: the payoff the CLI can only print once. -->
								{#if audit.result && !audit.result.passed && audit.result.sampleRows.length}
									<div>
										<div
											class="text-[var(--sb-text-faint)] pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
										>
											Violating rows — sample of {formatInteger(audit.result.failingRowCount)}
										</div>
										<div class="overflow-x-auto rounded-[3px] border border-border">
											<table class="w-full text-left">
												<thead>
													<tr class="bg-[var(--sb-surface-low)]">
														{#each audit.result.sampleColumns as column (column)}
															<th
																class="text-[var(--sb-text-faint)] border-b border-border px-2.5 py-1.5 font-mono text-[10px] font-normal"
																>{column}</th
															>
														{/each}
													</tr>
												</thead>
												<tbody>
													{#each audit.result.sampleRows as row, rowIndex (rowIndex)}
														<tr>
															{#each row as value, colIndex (colIndex)}
																<td
																	class="border-b border-[var(--border-subtle)] px-2.5 py-1.5 font-mono text-[11px]"
																	style:color={value === null || value === ''
																		? 'var(--sb-mono-err)'
																		: 'var(--foreground)'}>{cell(value)}</td
																>
															{/each}
														</tr>
													{/each}
												</tbody>
											</table>
										</div>
									</div>
								{/if}

								<SqlBlock
									artifacts={[{ label: 'Audit SQL', code: audit.sql }]}
									maxHeight="200px"
									caption={audit.file}
								/>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>

		<!-- ── tests ───────────────────────────────────────────────────────── -->
		<div>
			<div
				class="text-[var(--sb-text-faint)] flex items-baseline gap-2 pb-2 font-mono text-[10px] uppercase tracking-[0.14em]"
			>
				Tests
			</div>

			<div class="overflow-hidden rounded-[4px] border border-border">
				{#each visibleTests as test (test.name)}
					<div class="border-b border-[var(--border-subtle)] last:border-b-0">
						<button
							class="hover:bg-[var(--sb-hover)] flex w-full items-center gap-3 px-3 py-2 text-left"
							onclick={() => (expandedTest = expandedTest === test.name ? null : test.name)}
						>
							<span
								class="shrink-0 transition-transform"
								style:transform={expandedTest === test.name ? 'rotate(90deg)' : 'none'}
								><ChevronRightIcon size={12} class="text-muted-foreground" /></span
							>
							<span
								class="h-1.5 w-1.5 shrink-0 rounded-[2px]"
								style:background={!test.result
									? 'var(--border)'
									: test.result.passed
										? 'var(--sb-success)'
										: 'var(--sb-error)'}
							></span>
							<span class="min-w-0 flex-1 truncate text-[12px]">{test.name}</span>
							<span class="w-[200px] shrink-0 truncate font-mono text-[11px]">
								{#each test.targets as target, index (target)}
									<a href="/catalog/{target}" class="text-primary hover:underline"
										>{target}</a
									>{#if index < test.targets.length - 1}, {/if}
								{/each}
							</span>
							<span class="w-[70px] shrink-0 text-right font-mono text-[11px]">
								{#if !test.result}
									<span class="text-[var(--sb-text-faint)]">not run</span>
								{:else if test.result.passed}
									<span style:color="var(--sb-success)">pass</span>
								{:else}
									<span style:color="var(--sb-error)">fail</span>
								{/if}
							</span>
							<span class="text-[var(--sb-text-faint)] w-[74px] shrink-0 text-right font-mono text-[10.5px]"
								>{formatAgo(test.result?.checkedAt ?? null, project.capturedAt)}</span
							>
						</button>

						{#if expandedTest === test.name}
							<div class="flex flex-col gap-3 border-t border-[var(--border-subtle)] px-3 py-3">
								<div class="flex items-center gap-2">
									<button
										class="text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded-[4px] border border-border px-2 py-1 font-mono text-[10.5px] disabled:opacity-60"
										disabled={runningCheck !== null}
										onclick={() => void executeTest(test.name)}
									>
										{runningCheck === test.name ? 'running…' : 'run test'}
									</button>
								</div>
								{#if test.result && !test.result.passed}
									{#if test.result.errorMessage}
										<p class="font-mono text-[11px]" style:color="var(--sb-error)">
											{test.result.errorMessage}
										</p>
									{/if}
									<!-- Expected vs actual per compared target, side by side — the
									     shape the result model already has. -->
									{#each test.result.targets.filter((target) => !target.passed) as target (target.targetModelName)}
										<div>
											{#if test.result.targets.length > 1}
												<div class="code pb-1.5 text-[11px]">{target.targetModelName}</div>
											{/if}
											<div class="grid grid-cols-2 gap-3">
												<div>
													<div class="pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]" style:color="var(--sb-warning)">
														Missing — expected, not produced
													</div>
													{#if target.missingRows.length === 0}
														<p class="text-muted-foreground text-[11.5px]">none</p>
													{:else}
														<div class="overflow-x-auto rounded-[3px] border border-border">
															<table class="w-full text-left">
																<thead>
																	<tr class="bg-[var(--sb-surface-low)]">
																		{#each target.columns as column (column)}
																			<th
																				class="text-[var(--sb-text-faint)] border-b border-border px-2.5 py-1.5 font-mono text-[10px] font-normal"
																				>{column}</th
																			>
																		{/each}
																	</tr>
																</thead>
																<tbody>
																	{#each target.missingRows as row, rowIndex (rowIndex)}
																		<tr>
																			{#each row as value, colIndex (colIndex)}
																				<td
																					class="border-b border-[var(--border-subtle)] px-2.5 py-1.5 font-mono text-[11px]"
																					>{cell(value)}</td
																				>
																			{/each}
																		</tr>
																	{/each}
																</tbody>
															</table>
														</div>
													{/if}
												</div>
												<div>
													<div class="pb-1.5 font-mono text-[10px] uppercase tracking-[0.14em]" style:color="var(--sb-error)">
														Unexpected — produced, not expected
													</div>
													{#if target.unexpectedRows.length === 0}
														<p class="text-muted-foreground text-[11.5px]">none</p>
													{:else}
														<div class="overflow-x-auto rounded-[3px] border border-border">
															<table class="w-full text-left">
																<thead>
																	<tr class="bg-[var(--sb-surface-low)]">
																		{#each target.columns as column (column)}
																			<th
																				class="text-[var(--sb-text-faint)] border-b border-border px-2.5 py-1.5 font-mono text-[10px] font-normal"
																				>{column}</th
																			>
																		{/each}
																	</tr>
																</thead>
																<tbody>
																	{#each target.unexpectedRows as row, rowIndex (rowIndex)}
																		<tr>
																			{#each row as value, colIndex (colIndex)}
																				<td
																					class="border-b border-[var(--border-subtle)] px-2.5 py-1.5 font-mono text-[11px]"
																					style:color="var(--sb-mono-err)">{cell(value)}</td
																				>
																			{/each}
																		</tr>
																	{/each}
																</tbody>
															</table>
														</div>
													{/if}
												</div>
											</div>
										</div>
									{/each}
								{/if}

								<SqlBlock
									artifacts={[{ label: 'Test SQL', code: test.sql }]}
									maxHeight="240px"
									caption={test.file}
								/>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>
	</div>
</div>
