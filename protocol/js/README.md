# Job Protocol - JavaScript

JavaScript implementation of job description serialization/deserialization models.

## Classes

### `JobDescription`
Represents a single job listing.

**Constructor:**
```javascript
new JobDescription({ id, title, href })
```

**Methods:**
- `static fromDict(data)` - Create from plain object
- `toDict()` - Serialize to plain object

**Example:**
```javascript
const job = new JobDescription({
  id: 356182,
  title: "Lead Python Engineer",
  href: "https://jobs.dou.ua/companies/epam-systems/vacancies/356182/"
});

const obj = job.toDict();
const reconstructed = JobDescription.fromDict(obj);
```

### `JobDescriptionList`
Collection of job descriptions with JSON support.

**Methods:**
- `static fromList(data)` - Create from array of plain objects
- `static fromJson(jsonStr)` - Create from JSON string (expects array)
- `toList()` - Serialize to array of plain objects
- `toJson()` - Serialize to JSON string

**Example:**
```javascript
const payload = JSON.stringify([
  { id: 1, title: "Job 1", href: "..." },
  { id: 2, title: "Job 2", href: "..." }
]);

const jobs = JobDescriptionList.fromJson(payload);
const jsonOut = jobs.toJson();
```

## Testing

Run tests with:
```bash
npm test
```

Tests include:
- Single object serialization/deserialization
- List serialization/deserialization  
- JSON round-trip serialization
- Error handling for invalid payloads

