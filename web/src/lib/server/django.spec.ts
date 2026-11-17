import { describe, expect, it } from 'vitest';
import { djangoCall, isDjangoPath } from './django';

const visitor = {
	url: new URL('https://floppy.example/next/'),
	address: '203.0.113.7',
	cookie: 'sessionid=visitor'
};

describe('djangoCall', () => {
	it('sends API calls to Django on loopback as nginx would', () => {
		const request = new Request('https://floppy.example/api/v1/user/account/?x=1', {
			headers: { cookie: 'sessionid=abc', 'x-real-ip': '6.6.6.6' }
		});

		const call = djangoCall(request, visitor, 'http://127.0.0.1:8001');

		expect(call?.target.href).toBe('http://127.0.0.1:8001/api/v1/user/account/?x=1');
		expect(call?.headers.host).toBe('floppy.example');
		expect(call?.headers['x-forwarded-proto']).toBe('https');
		expect(call?.headers['x-real-ip']).toBe('203.0.113.7');
		expect(call?.headers.cookie).toBe('sessionid=abc');
	});

	it("passes the visitor's cookie on when the request has none", () => {
		const call = djangoCall(new Request('https://floppy.example/_allauth/browser/v1/auth/session'), visitor);

		expect(call?.headers.cookie).toBe('sessionid=visitor');
	});

	it('leaves other sites and SvelteKit routes alone', () => {
		expect(djangoCall(new Request('https://api.themoviedb.org/api/v1/x'), visitor)).toBeNull();
		expect(djangoCall(new Request('https://floppy.example/next/health'), visitor)).toBeNull();
	});

	it('knows which paths are Django', () => {
		expect(isDjangoPath('/_allauth/browser/v1/auth/session')).toBe(true);
		expect(isDjangoPath('/api/v1/info/')).toBe(true);
		expect(isDjangoPath('/admin/')).toBe(false);
	});
});
