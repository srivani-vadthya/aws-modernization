---
name: page-with-form
description: "Full page component pattern for form-based pages: config-driven state, deepClone init, validateFormFields on submit, React Router navigation"
tags: ["page", "form", "controller", "login", "registration", "submit", "navigate", "validation"]
trigger: page_controller_with_form
---

# Page With Form — Golden Pattern

## When to Apply
Any legacy Angular controller that:
- Has `ng-submit` or a submit handler
- Maps form fields to `$scope` properties
- Calls a service on success then routes to another page

## Exact Golden Pattern

```tsx
// filepath: src/pages/Login/Login.tsx
import { useState, type ChangeEvent, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import loginConfig from '../../config/login.json';
import { deepClone } from '../../scripts/utils';
import { validateFormFields } from '../../scripts/validationsService';
import Card from '../../common/components/Card';
import Typography from '../../common/components/Typography/Typography';
import CardContent from '../../common/components/Card/CardContent';
import TextField from '../../common/components/TextField/TextField';
import Button from '../../common/components/Button/Button';
import Select from '../../common/components/Select';

type FormDataType = typeof loginConfig;

const Login = () => {
    const navigate = useNavigate();
    // Deep clone the config to avoid mutating the original JSON
    const clonedLoginConfig = deepClone(loginConfig);

    // Initialize form data from JSON configuration
    const [formData, setFormData] = useState<FormDataType>(clonedLoginConfig);

    const handleInputChange = (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const { id, value } = e.target;
        setFormData(prevData => ({
            ...prevData,
            [id as keyof FormDataType]: {
                ...prevData[id as keyof FormDataType],
                value,
                hasError: false,
                errorMessage: '',
            },
        }));
    };

    const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();

        // validateFormFields returns { data, status } — status=true means all valid
        const { data, status } = validateFormFields(formData);

        if (status) {
            setFormData(clonedLoginConfig);   // reset after success
            navigate('/home');                // route to next page
        } else {
            // Map validation errors back onto form fields
            setFormData(prevData =>
                Object.entries(prevData).reduce((acc, [key, field], index) => {
                    const validationResult = data[index] as
                        | { isValid: boolean; errorMessage?: string }
                        | undefined;
                    return {
                        ...acc,
                        [key]: {
                            ...field,
                            hasError: !validationResult?.isValid,
                            errorMessage: validationResult?.errorMessage || '',
                        },
                    };
                }, {} as FormDataType),
            );
        }
    };

    return (
        <div className='min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 p-4'>
            <div className='w-auto'>
                <Card
                    variant='outlined'
                    className='bg-white rounded-xl shadow-2xl overflow-hidden w-[420px]'
                >
                    <div className='px-6 py-2 bg-gradient-to-r from-blue-50 to-indigo-50'>
                        <Typography variant='h1' className='text-center text-gray-900'>
                            Login
                        </Typography>
                    </div>

                    <form onSubmit={handleSubmit} noValidate>
                        <CardContent className='p-8 gap-4 flex flex-col'>
                            <TextField {...formData.email} onChange={handleInputChange} />
                            <TextField {...formData.password} onChange={handleInputChange} />
                            <Select {...formData.city} onChange={handleInputChange} />
                        </CardContent>
                        <CardContent className='border-t border-gray-200 px-8 py-6 bg-gray-50'>
                            <Button
                                variant='contained'
                                color='primary'
                                size='medium'
                                fullWidth
                                type='submit'
                                id='submit'
                            >
                                Login
                            </Button>
                        </CardContent>
                    </form>
                </Card>
            </div>
        </div>
    );
};

export default Login;
```

## Key Rules Enforced By This Pattern
1. **Always** import form config from `../../config/<pageName>.json`
2. **Always** use `deepClone(config)` — never mutate the imported JSON directly
3. **Always** call `validateFormFields(formData)` on submit — never inline validation logic
4. **Always** spread the config field `{...formData.fieldName}` into TextField/Select — never pass props individually
5. Use `useNavigate()` for post-submit routing — never `window.location`
