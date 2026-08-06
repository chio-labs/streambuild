/**
 * Correctness harness for the lane ordering solver.
 *
 *   npm run verify:lanes
 *
 * `orderLanes` solves weighted Minimum Linear Arrangement with a subset DP.
 * The identity it rests on (an edge's span equals the number of prefix cuts it
 * crosses) plus the bit manipulation make it the kind of code that returns a
 * plausible-but-suboptimal answer when it is wrong, which no screenshot would
 * catch. So it is checked against a brute force over every permutation.
 *
 * Run with Node's built-in type stripping; the module under test has no imports
 * of its own, so no bundler or alias resolution is involved.
 */

import {
	orderLanes,
	solveExact,
	solveHeuristic,
	weightKey,
	arrangementCost,
	type LaneWeights
} from '../src/lib/lineage/lane-order.ts';

function bruteForceCost(groups: string[], weights: LaneWeights): number {
	let best: number = Infinity;
	const permute = (rest: string[], acc: string[]): void => {
		if (rest.length === 0) {
			best = Math.min(best, arrangementCost(acc, weights));
			return;
		}
		for (let i = 0; i < rest.length; i += 1) {
			permute([...rest.slice(0, i), ...rest.slice(i + 1)], [...acc, rest[i]]);
		}
	};
	permute(groups, []);
	return best;
}

/** Deterministic LCG so a failure is reproducible. */
let seed: number = 20260802;
function random(): number {
	seed = (seed * 1103515245 + 12345) & 0x7fffffff;
	return seed / 0x7fffffff;
}

function randomCase(laneCount: number): { groups: string[]; weights: LaneWeights } {
	const groups: string[] = Array.from({ length: laneCount }, (_, i) => `p${i}`);
	const weights: LaneWeights = new Map();
	for (let i = 0; i < laneCount; i += 1) {
		for (let j = i + 1; j < laneCount; j += 1) {
			if (random() < 0.45) {
				weights.set(weightKey(groups[i], groups[j]), 1 + Math.floor(random() * 4));
			}
		}
	}
	return { groups, weights };
}

let failures: number = 0;

// ── exact solver matches brute force ────────────────────────────────────────
const TRIALS: number = 500;
let suboptimal: number = 0;
for (let trial = 0; trial < TRIALS; trial += 1) {
	const laneCount: number = 3 + Math.floor(random() * 6);
	const { groups, weights } = randomCase(laneCount);
	const got: number = arrangementCost(orderLanes(groups, weights), weights);
	const want: number = bruteForceCost(groups, weights);
	if (got !== want) {
		suboptimal += 1;
		if (suboptimal <= 3) console.log(`  suboptimal: n=${laneCount} got=${got} want=${want}`);
	}
}
if (suboptimal > 0) failures += 1;
console.log(`${suboptimal === 0 ? '✓' : '✗'} exact solver  ${TRIALS - suboptimal}/${TRIALS} optimal`);

// ── output is a permutation of the input ────────────────────────────────────
{
	const { groups, weights } = randomCase(9);
	const result: string[] = orderLanes(groups, weights);
	const same: boolean =
		result.length === groups.length && [...result].sort().join() === [...groups].sort().join();
	if (!same) failures += 1;
	console.log(`${same ? '✓' : '✗'} permutation   every lane appears exactly once`);
}

// ── strongly connected lanes end up adjacent ────────────────────────────────
{
	const weights: LaneWeights = new Map([
		[weightKey('a', 'd'), 5],
		[weightKey('b', 'c'), 1]
	]);
	const result: string[] = orderLanes(['a', 'b', 'c', 'd'], weights);
	const adjacent: boolean = Math.abs(result.indexOf('a') - result.indexOf('d')) === 1;
	if (!adjacent) failures += 1;
	console.log(`${adjacent ? '✓' : '✗'} adjacency     heaviest pair neighbours in [${result.join(' ')}]`);
}

// ── orientation is stable, not an arbitrary reflection ──────────────────────
{
	const weights: LaneWeights = new Map([
		[weightKey('src', 'mid'), 3],
		[weightKey('mid', 'sink'), 3]
	]);
	const forward: string[] = orderLanes(['src', 'mid', 'sink'], weights);
	const upstreamFirst: boolean = forward.indexOf('src') < forward.indexOf('sink');
	if (!upstreamFirst) failures += 1;
	console.log(`${upstreamFirst ? '✓' : '✗'} orientation   seed order preserved in [${forward.join(' ')}]`);
}

// ── the fallback stays close to optimal where both solvers can run ──────────
{
	const SAMPLES: number = 60;
	let worstGap: number = 0;
	let exactMatches: number = 0;
	for (let trial = 0; trial < SAMPLES; trial += 1) {
		const { groups, weights } = randomCase(12 + Math.floor(random() * 5));
		const best: number = arrangementCost(solveExact(groups, weights), weights);
		const approx: number = arrangementCost(solveHeuristic(groups, weights), weights);
		if (approx === best) exactMatches += 1;
		if (best > 0) worstGap = Math.max(worstGap, (approx - best) / best);
	}
	const acceptable: boolean = worstGap <= 0.05;
	if (!acceptable) failures += 1;
	console.log(
		`${acceptable ? '✓' : '✗'} fallback      ${exactMatches}/${SAMPLES} optimal, worst gap ${(worstGap * 100).toFixed(1)}%`
	);
}

// ── the large-graph fallback stays responsive ───────────────────────────────
{
	const { groups, weights } = randomCase(40);
	const started: number = performance.now();
	orderLanes(groups, weights);
	const elapsed: number = performance.now() - started;
	const quick: boolean = elapsed < 2000;
	if (!quick) failures += 1;
	console.log(`${quick ? '✓' : '✗'} heuristic     40 lanes in ${elapsed.toFixed(0)}ms`);
}

process.exit(failures > 0 ? 1 : 0);
