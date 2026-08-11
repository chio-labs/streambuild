/**
 * Lane ordering: put strongly connected pipelines next to each other.
 *
 * In lanes mode the x axis already carries dependency depth (dagre ranks the
 * whole graph globally), so the vertical order of the lanes is free. Spending
 * it well means minimising how far edges have to travel vertically:
 *
 *     cost(order) = Σ over cross-lane edges  w(a,b) · |pos(a) − pos(b)|
 *
 * That is the weighted Minimum Linear Arrangement problem. It is NP-hard in
 * general, but the graph here is the PIPELINE quotient graph — one vertex per
 * pipeline, not per model — so n is small enough to solve exactly.
 */

/** Undirected pipeline-to-pipeline edge counts, keyed by `a\u0000b` with a < b. */
export type LaneWeights = Map<string, number>;

/**
 * Above this many lanes the exact solver is abandoned for local search.
 * 2^16 subsets is ~0.5MB and a few million operations — imperceptible. Real
 * projects sit far below this; the fallback exists so a pathological project
 * degrades in quality rather than hanging the tab.
 */
const EXACT_LIMIT = 16;

export function weightKey(a: string, b: string): string {
	return a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`;
}

function weightBetween(weights: LaneWeights, a: string, b: string): number {
	return weights.get(weightKey(a, b)) ?? 0;
}

export function arrangementCost(order: string[], weights: LaneWeights): number {
	let total: number = 0;
	for (let i = 0; i < order.length; i += 1) {
		for (let j = i + 1; j < order.length; j += 1) {
			total += weightBetween(weights, order[i], order[j]) * (j - i);
		}
	}
	return total;
}

/**
 * Exact solver.
 *
 * Uses the identity that an edge's span equals the number of prefix cuts it
 * crosses, so the total cost is Σ cut(prefix) over every proper prefix of the
 * ordering. That turns the problem into a subset DP over which lanes have been
 * placed so far, independent of the order WITHIN the prefix:
 *
 *     f(S) = min over v ∈ S of  f(S \ {v}) + cut(S \ {v})
 *
 * O(2^n · n), which is the standard Held-Karp shape.
 *
 * Exported so the harness can measure the fallback against it directly.
 */
export function solveExact(groups: string[], weights: LaneWeights): string[] {
	const n: number = groups.length;
	const size: number = 1 << n;

	const pair: Float64Array = new Float64Array(n * n);
	const degree: Float64Array = new Float64Array(n);
	for (let i = 0; i < n; i += 1) {
		for (let j = i + 1; j < n; j += 1) {
			const weight: number = weightBetween(weights, groups[i], groups[j]);
			pair[i * n + j] = weight;
			pair[j * n + i] = weight;
			degree[i] += weight;
			degree[j] += weight;
		}
	}

	// cut[S] = total weight of edges with exactly one endpoint in S, built
	// incrementally from the subset with the lowest set bit removed.
	const cut: Float64Array = new Float64Array(size);
	for (let subset = 1; subset < size; subset += 1) {
		const low: number = subset & -subset;
		const bit: number = 31 - Math.clz32(low);
		const rest: number = subset ^ low;
		let shared: number = 0;
		for (let other = rest; other !== 0; ) {
			const otherLow: number = other & -other;
			shared += pair[bit * n + (31 - Math.clz32(otherLow))];
			other ^= otherLow;
		}
		cut[subset] = cut[rest] + degree[bit] - 2 * shared;
	}

	const best: Float64Array = new Float64Array(size).fill(Infinity);
	const pick: Int8Array = new Int8Array(size).fill(-1);
	best[0] = 0;

	for (let subset = 1; subset < size; subset += 1) {
		// `groups` arrives in the caller's preferred order, and candidates are
		// tried in that order with a strict improvement test, so ties resolve
		// toward the seed ordering rather than arbitrarily.
		for (let bit = 0; bit < n; bit += 1) {
			const mask: number = 1 << bit;
			if ((subset & mask) === 0) continue;
			const rest: number = subset ^ mask;
			const candidate: number = best[rest] + cut[rest];
			if (candidate < best[subset]) {
				best[subset] = candidate;
				pick[subset] = bit;
			}
		}
	}

	const order: string[] = [];
	for (let subset = size - 1; subset > 0; ) {
		const bit: number = pick[subset];
		order.push(groups[bit]);
		subset ^= 1 << bit;
	}
	order.reverse();
	return order;
}

/**
 * Fallback for graphs too large for the exact solver.
 *
 * Local search over two neighbourhoods — reinserting a lane elsewhere, and
 * exchanging a pair of lanes — restarted from several seeds. Reinsertion alone
 * from a single seed settles into local minima that were measurably off
 * optimal on dense graphs; the swap neighbourhood and the restarts are what
 * close that gap.
 *
 * Exported so the harness can measure its quality gap against the exact solver.
 */
export function solveHeuristic(groups: string[], weights: LaneWeights): string[] {
	const n: number = groups.length;
	const indexOf = new Map<string, number>(groups.map((key, index) => [key, index]));

	// Score against the sparse edge list rather than all n² pairs: the quotient
	// graph of a real project is nowhere near complete, and this loop is the
	// innermost term of the search.
	const edgeA: Int32Array = new Int32Array(weights.size);
	const edgeB: Int32Array = new Int32Array(weights.size);
	const edgeW: Float64Array = new Float64Array(weights.size);
	let edgeCount: number = 0;
	for (const [key, weight] of weights) {
		const [a, b] = key.split('\u0000');
		const ia: number | undefined = indexOf.get(a);
		const ib: number | undefined = indexOf.get(b);
		if (ia === undefined || ib === undefined) continue;
		edgeA[edgeCount] = ia;
		edgeB[edgeCount] = ib;
		edgeW[edgeCount] = weight;
		edgeCount += 1;
	}

	const position: Int32Array = new Int32Array(n);
	const costOf: (candidate: Int32Array) => number = (candidate: Int32Array): number => {
		for (let slot = 0; slot < n; slot += 1) position[candidate[slot]] = slot;
		let total: number = 0;
		for (let e = 0; e < edgeCount; e += 1) {
			total += edgeW[e] * Math.abs(position[edgeA[e]] - position[edgeB[e]]);
		}
		return total;
	};

	// Reinsertion is windowed because long-range moves are both the expensive
	// ones and rarely the improving ones. Swaps are unrestricted: they are only
	// O(n²) candidates and they are what escape the reinsertion minima.
	const WINDOW: number = 8;
	const MAX_PASSES: number = 12;

	const trial: Int32Array = new Int32Array(n);

	const refine: (seed: Int32Array) => { order: Int32Array; cost: number } = (
		seed: Int32Array
	): { order: Int32Array; cost: number } => {
		let order: Int32Array = Int32Array.from(seed);
		let cost: number = costOf(order);

		for (let pass = 0; pass < MAX_PASSES; pass += 1) {
			let improved: boolean = false;

			for (let from = 0; from < n; from += 1) {
				const lowest: number = Math.max(0, from - WINDOW);
				const highest: number = Math.min(n - 1, from + WINDOW);
				for (let to = lowest; to <= highest; to += 1) {
					if (to === from) continue;
					trial.set(order);
					const moved: number = trial[from];
					if (to > from) trial.copyWithin(from, from + 1, to + 1);
					else trial.copyWithin(to + 1, to, from);
					trial[to] = moved;
					const trialCost: number = costOf(trial);
					if (trialCost < cost) {
						order = Int32Array.from(trial);
						cost = trialCost;
						improved = true;
					}
				}
			}

			for (let a = 0; a < n; a += 1) {
				for (let b = a + 1; b < n; b += 1) {
					trial.set(order);
					trial[a] = order[b];
					trial[b] = order[a];
					const trialCost: number = costOf(trial);
					if (trialCost < cost) {
						order = Int32Array.from(trial);
						cost = trialCost;
						improved = true;
					}
				}
			}

			if (!improved) break;
		}
		return { order, cost };
	};

	// Restart 0 is the caller's seed, so a good depth ordering is never lost.
	// The rest are shuffles from a fixed-seed generator, which keeps the layout
	// deterministic across reloads — a graph that reshuffles itself on every
	// render is worse than one that is slightly suboptimal.
	const RESTARTS: number = 6;
	let random: number = 0x2f6e2b1;
	const nextRandom: () => number = (): number => {
		random ^= random << 13;
		random ^= random >>> 17;
		random ^= random << 5;
		return (random >>> 0) / 0x100000000;
	};

	const identity: Int32Array = new Int32Array(n).map((_, index) => index);
	let best: { order: Int32Array; cost: number } = refine(identity);

	for (let restart = 1; restart < RESTARTS; restart += 1) {
		const shuffled: Int32Array = Int32Array.from(identity);
		for (let i = n - 1; i > 0; i -= 1) {
			const j: number = Math.floor(nextRandom() * (i + 1));
			const swap: number = shuffled[i];
			shuffled[i] = shuffled[j];
			shuffled[j] = swap;
		}
		const candidate: { order: Int32Array; cost: number } = refine(shuffled);
		if (candidate.cost < best.cost) best = candidate;
	}

	return Array.from(best.order, (index) => groups[index]);
}

/**
 * Reversing an ordering leaves its cost identical, so orientation is free to
 * choose. Pick the direction that reads with the flow: upstream pipelines at
 * the top, measured against the seed's depth ordering.
 */
function orientWithDepth(order: string[], depthRank: Map<string, number>): string[] {
	let agreement: number = 0;
	for (let i = 0; i < order.length; i += 1) {
		for (let j = i + 1; j < order.length; j += 1) {
			const a: number = depthRank.get(order[i]) ?? 0;
			const b: number = depthRank.get(order[j]) ?? 0;
			if (a < b) agreement += 1;
			else if (a > b) agreement -= 1;
		}
	}
	return agreement < 0 ? order.slice().reverse() : order;
}

/**
 * @param seed lanes in the caller's preferred order (depth-sorted), which acts
 *   as both the tie-break and the orientation reference.
 */
export function orderLanes(seed: string[], weights: LaneWeights): string[] {
	if (seed.length < 3) return seed;

	const depthRank = new Map<string, number>(seed.map((key, index) => [key, index]));
	const solved: string[] =
		seed.length <= EXACT_LIMIT ? solveExact(seed, weights) : solveHeuristic(seed, weights);

	return orientWithDepth(solved, depthRank);
}
