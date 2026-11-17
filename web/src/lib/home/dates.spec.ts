import { describe, expect, it } from 'vitest';
import { comingDay, dayOfMonth, weekday } from './dates.ts';

describe('release day labels', () => {
	it('read the day as a calendar date, whatever the time zone', () => {
		expect(weekday('2026-11-18')).toBe('Wed');
		expect(dayOfMonth('2026-11-18')).toBe('18');
		expect(comingDay('2026-12-01')).toBe('Tue 1 Dec');
	});
});
