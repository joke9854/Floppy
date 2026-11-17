/**
 * Day labels for releases. The API sends the local release day as
 * `YYYY-MM-DD`; it is read as a calendar date, never through a time zone, so
 * the label is the day the server counted.
 */
function calendarDate(day: string): Date {
	const [year, month, date] = day.split('-').map(Number);
	return new Date(Date.UTC(year, month - 1, date));
}

const format = (day: string, options: Intl.DateTimeFormatOptions) =>
	new Intl.DateTimeFormat('en-GB', { ...options, timeZone: 'UTC' }).format(calendarDate(day));

/** "Tue", as the Django row's `D`. */
export const weekday = (day: string) => format(day, { weekday: 'short' });

/** "18", as the Django row's `j`. */
export const dayOfMonth = (day: string) => String(calendarDate(day).getUTCDate());

/** "Tue 18 Nov", as the Coming Soon pill's `D j M`. */
export const comingDay = (day: string) =>
	`${weekday(day)} ${dayOfMonth(day)} ${format(day, { month: 'short' })}`;
