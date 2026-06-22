---
name: guard
description: Security-first mindset. Protect secrets, validate inputs, prevent injection attacks, enforce least privilege. Use when handling sensitive data or external inputs.
---

# Guard

## Security Mindset

**Assume every input is malicious. Trust nothing, verify everything.**

## Critical Rules

### 1. Never Expose Secrets
❌ **CRITICAL**: Hardcoded passwords, API keys, tokens
```javascript
// ❌ NEVER DO THIS
const apiKey = "sk-1234567890abcdef";
const dbPassword = "admin123";
```

✅ **CORRECT**: Use environment variables or secret managers
```javascript
const apiKey = process.env.SAP_API_KEY;
const dbPassword = process.env.DB_PASSWORD;

// Validate they exist
if (!apiKey) throw new Error("SAP_API_KEY not configured");
```

### 2. Validate ALL Inputs
```typescript
// At every system boundary (API, user input, file upload, external API)
function validateInput(input: unknown): Result<SanitizedInput, Error> {
  // Type check
  if (typeof input !== 'object' || input === null) {
    return failure(new ValidationError("Invalid input type"));
  }
  
  // Required fields
  const { userId, action } = input as any;
  if (!userId || !action) {
    return failure(new ValidationError("Missing required fields"));
  }
  
  // Type validation
  if (typeof userId !== 'string' || userId.length > 36) {
    return failure(new ValidationError("Invalid userId"));
  }
  
  // Whitelist allowed values
  const allowedActions = ['read', 'write', 'delete'];
  if (!allowedActions.includes(action)) {
    return failure(new ValidationError("Invalid action"));
  }
  
  // Sanitize
  return success({
    userId: sanitizeString(userId),
    action: action
  });
}
```

### 3. Prevent Injection Attacks

#### SQL Injection
```javascript
// ❌ VULNERABLE
const query = `SELECT * FROM users WHERE id = '${userId}'`;

// ✅ SAFE - Parameterized queries
const query = 'SELECT * FROM users WHERE id = $1';
const result = await db.query(query, [userId]);
```

#### XSS (Cross-Site Scripting)
```javascript
// ❌ VULNERABLE
element.innerHTML = userInput;

// ✅ SAFE - Escape or use textContent
element.textContent = userInput;
// OR use a sanitization library
element.innerHTML = DOMPurify.sanitize(userInput);
```

#### Command Injection
```javascript
// ❌ VULNERABLE
exec(`ls ${userInput}`);

// ✅ SAFE - Avoid shell, use arrays
spawn('ls', [userInput], { shell: false });
```

### 4. Authentication & Authorization

#### Always Verify Identity
```typescript
// Middleware pattern
async function authenticate(req, res, next) {
  const token = req.headers.authorization?.split(' ')[1];
  if (!token) {
    return res.status(401).json({ error: "Authentication required" });
  }
  
  try {
    const user = await verifyToken(token);
    req.user = user;
    next();
  } catch (error) {
    return res.status(401).json({ error: "Invalid token" });
  }
}
```

#### Enforce Permissions
```typescript
// Check authorization for EVERY action
async function deleteUser(requestingUser, targetUserId) {
  // Admin can delete anyone
  // Users can delete themselves
  if (requestingUser.role !== 'admin' && requestingUser.id !== targetUserId) {
    throw new ForbiddenError("Cannot delete other users");
  }
  
  // Proceed with deletion
  await db.users.delete(targetUserId);
}
```

### 5. Rate Limiting
```javascript
// Prevent abuse
const rateLimiter = new RateLimiter({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100 // limit each IP to 100 requests per windowMs
});

app.use('/api/', rateLimiter.middleware);
```

## Security Checklist

### Before Deployment
- [ ] No secrets in code (use .env, AWS Secrets Manager, etc.)
- [ ] All inputs validated and sanitized
- [ ] Authentication required for sensitive endpoints
- [ ] Authorization checked for every action
- [ ] Rate limiting enabled
- [ ] CORS configured (not `*` in production)
- [ ] HTTPS enforced
- [ ] Security headers set (CSP, HSTS, X-Frame-Options)
- [ ] Dependencies updated (no known vulnerabilities)
- [ ] Error messages don't leak sensitive info

### Data Handling
- [ ] Sensitive data encrypted at rest
- [ ] Data encrypted in transit (TLS)
- [ ] Personal data handled per GDPR/privacy laws
- [ ] Data minimization (collect only what's needed)
- [ ] Data retention policy (delete old data)

### Logging
- [ ] No passwords, tokens, or PII in logs
- [ ] Log authentication attempts (success/failure)
- [ ] Log authorization failures
- [ ] Log suspicious activity
- [ ] Logs are secure and access-controlled

## Common Vulnerabilities (OWASP Top 10)

### 1. Broken Access Control
**Problem**: Users can access data they shouldn't  
**Fix**: Enforce authorization checks on every request

### 2. Cryptographic Failures
**Problem**: Sensitive data not encrypted  
**Fix**: Use TLS, encrypt passwords (bcrypt), encrypt sensitive fields

### 3. Injection
**Problem**: Untrusted data sent to interpreter  
**Fix**: Parameterized queries, input validation, output encoding

### 4. Insecure Design
**Problem**: Missing security controls in architecture  
**Fix**: Threat modeling, security review during design

### 5. Security Misconfiguration
**Problem**: Default passwords, verbose errors, open ports  
**Fix**: Hardened configs, disable defaults, minimal permissions

### 6. Vulnerable Components
**Problem**: Outdated dependencies with known CVEs  
**Fix**: Regular updates, dependency scanning (npm audit, Snyk)

### 7. Authentication Failures
**Problem**: Weak passwords, session hijacking  
**Fix**: MFA, strong password policy, secure session management

### 8. Data Integrity Failures
**Problem**: Data tampered in transit or storage  
**Fix**: Digital signatures, checksums, immutable logs

### 9. Logging Failures
**Problem**: Can't detect breaches or investigate incidents  
**Fix**: Comprehensive logging, monitoring, alerting

### 10. SSRF
**Problem**: Server makes requests to internal resources  
**Fix**: Validate URLs, whitelist allowed hosts, network segmentation

## SAP EWM Specific Security

### OData API Security
```typescript
// Always use authenticated sessions
const sapClient = axios.create({
  baseURL: process.env.SAP_EWM_URL,
  auth: {
    username: process.env.SAP_USERNAME,
    password: process.env.SAP_PASSWORD
  },
  httpsAgent: new https.Agent({
    rejectUnauthorized: true // Don't disable in production!
  })
});
```

### MQTT Security (Robot Communication)
```javascript
// Secure MQTT connection
const mqttClient = mqtt.connect('mqtts://mqtt.example.com', {
  username: process.env.MQTT_USER,
  password: process.env.MQTT_PASSWORD,
  clientId: `dispatch_${uuid.v4()}`,
  rejectUnauthorized: true,
  protocolVersion: 4
});

// Subscribe only to needed topics
mqttClient.subscribe('vda5050/+/state'); // All AGV states
mqttClient.subscribe('vda5050/+/orders'); // All AGV orders
```

### VDA5050 Message Validation
```typescript
// Validate robot messages before processing
function validateVDA5050State(state: unknown): Result<VDA5050State, Error> {
  const schema = z.object({
    headerId: z.number(),
    timestamp: z.string().datetime(),
    version: z.string(),
    manufacturer: z.string(),
    serialNumber: z.string(),
    state: z.enum(['IDLE', 'RUNNING', 'ERROR']),
    batteryState: z.object({
      batteryCharge: z.number().min(0).max(100),
      charging: z.boolean()
    })
  });
  
  const validation = schema.safeParse(state);
  if (!validation.success) {
    return failure(new ValidationError(validation.error.message));
  }
  
  return success(validation.data);
}
```

## Incident Response

### When You Discover a Vulnerability
1. **STOP** - Don't deploy, don't commit
2. **ASSESS** - How severe? What's exposed?
3. **FIX** - Patch immediately
4. **TEST** - Verify the fix works
5. **DEPLOY** - Get it to production ASAP
6. **REVIEW** - How did it happen? Prevent recurrence

### Security Breach Response
1. Contain the breach (rotate secrets, block access)
2. Assess impact (what data was exposed?)
3. Notify affected parties (users, regulators if required)
4. Fix the vulnerability
5. Document and learn

## Tools

### Scanning
- `npm audit` - Check for vulnerable dependencies
- `npm audit fix` - Auto-fix vulnerabilities
- `snyk test` - Advanced vulnerability scanning
- `eslint-plugin-security` - Static analysis

### Testing
- Penetration testing (manual or automated)
- OWASP ZAP - Web app security scanner
- Burp Suite - Security testing platform

## Golden Rules

1. **Secrets in environment, never in code**
2. **Validate at every boundary**
3. **Least privilege principle**
4. **Defense in depth** (multiple security layers)
5. **Assume breach** (design for detection and response)
6. **Keep it simple** (complexity breeds vulnerabilities)
7. **Stay updated** (dependencies, security advisories)
8. **Log security events** (but not sensitive data)
